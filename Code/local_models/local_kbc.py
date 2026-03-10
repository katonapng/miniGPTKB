import json
import os
import queue
import re
import threading
import time
from pathlib import Path

import validators
from openai import OpenAI

from Code.GUI.logger_setup import logger
from Code.local_models.dataclass import PathConfig, RunConfig

api_key = os.getenv("MY_API_KEY")
if api_key is None:
    logger.error("API key not found! Set MY_API_KEY in environment variables.")
else:
    logger.info("API key loaded successfully.")


# === CONFIGURATION ===
max_iterations = 10  # no limits
verbose = True
nthreads = 5


# === LLM WRAPPER ===
def prompt_llm_local(main_config):
    client = OpenAI(base_url=main_config.url, api_key=api_key)
    r = client.chat.completions.create(
        messages=[{"role": "user", "content": main_config.prompt}],
        model=main_config.model,
        temperature=0
    )
    return r.choices[0].message.content


# === FILE UTILS ===
def append_to_jsonl_file(file_path, new_data):
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(json.dumps(new_data) + '\n')


def remove_json_delimiters(s: str):
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


def read_first_n_subjects(subject_queue, n):
    if n <= 0:
        return []  # return empty list for non-positive n
    return subject_queue[:n]


def delete_first_n_subjects(subject_queue, n):
    if n <= 0 or n >= len(subject_queue):
        return []
    return subject_queue[n:]


def define_file_paths(run_dir):
    timestamp_dir = run_dir / f"run-{time.strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(timestamp_dir, exist_ok=True)
    subject_queue_path = timestamp_dir / "subjectQueue.json"
    processed_subjects_path = timestamp_dir / "processedSubjects.json"
    triples_output_path = timestamp_dir / "triples.jsonl"
    parse_errors_path = timestamp_dir / "batchResultParseErrors.jsonl"
    not_ne_path = timestamp_dir / "notNE.jsonl"

    return (
        subject_queue_path,
        processed_subjects_path,
        triples_output_path,
        parse_errors_path,
        not_ne_path
    )


# === MAIN FUNCTION: TRIPLE EXTRACTION ===
def get_triples(
    subject, result_queue, error_queue, path_config, main_config,
):
    main_config.prompt = (
        f'I want to construct a knowledge graph on the topic of '
        f'the {main_config.topic}. '
        'Given a subject entity, return all facts that you know '
        'for the subject as a list of subject, predicate, object '
        'triples. The number of facts may be very high, between '
        f'{main_config.min_triples} to {main_config.max_triples} or more, for very popular '
        'subjects. For less popular subjects, the number of facts '
        'can be very low, like 5 or 10.\n\n'
        'Important: \n- If you don\'t know the subject, return an '
        'empty list. \n- If the subject is not a named entity, '
        'return an empty list.\n'
        f'- If the subject does not belong to the topic of the '
        f'{main_config.topic}, return an empty list.\n'
        '- If the subject is a named entity, include at least one '
        'triple where predicate is "instanceOf".\n'
        '- Do not get too wordy.\n- Separate several objects into '
        'multiple triples with one object.\n'
        '- Format the output as a structured JSON, a list of '
        'dictionaries with 3 keys "s", "p", and "o" each, and '
        'the respective values.\n'
        '- Don\'t generate any other text except for the triples '
        'in JSON format.\n'
        f'Subject: "{subject}"'
    )
    logger.info(f"Querying subject: {subject}")
    try:
        output_string = prompt_llm_local(main_config)
        try:
            linetriples = json.loads(remove_json_delimiters(output_string))
            result_queue.put(linetriples)
            logger.info(
                f"   Received {len(linetriples)} triples for: {subject}"
            )
        except Exception as e:
            error_data = {
                "error": str(e),
                "line": str(output_string)
            }
            append_to_jsonl_file(path_config.parse_errors_path, error_data)
            result_queue.put([])
            logger.warning(f"   Failed to parse JSON for: {subject}")
    except Exception as e:
        error_queue.put(e)
        logger.exception(f"Exception during prompt for subject: {subject}")


# === DEDUPLICATION ===
def deduplicate_triples(triples):
    seen = set()
    unique_triples = []
    for t in triples:
        try:
            key = (
                t.get('s', '').strip(),
                t.get('p', '').strip(),
                t.get('o', '').strip()
            )
            if key not in seen:
                seen.add(key)
                unique_triples.append(t)
        except Exception as e:
            logger.error(f"Error processing triple {t}: {e}")
            continue
    return unique_triples


def store_triples(newTriples, triples_output_path):
    unique_triples = deduplicate_triples(newTriples)
    dedup_count = len(newTriples) - len(unique_triples)
    logger.info(
        f"   Deduplicated {dedup_count} triples "
        f"(from {len(newTriples)} to {len(unique_triples)})"
    )
    with open(triples_output_path, 'w', encoding='utf8') as file:
        for obj in unique_triples:
            file.write(json.dumps(obj) + '\n')


def append_to_processed_subjects(
        processed_subjects, subjects, processed_subjects_path
):
    processed_subjects.extend(subjects)
    with open(processed_subjects_path, 'w', encoding='utf-8') as file:
        json.dump(processed_subjects, file, ensure_ascii=False, indent=2)
    return processed_subjects


def append_to_subject_queue(subject_queue, newSubjects, subject_queue_path):
    subject_queue.extend(newSubjects)
    with open(subject_queue_path, 'w', encoding='utf-8') as file:
        json.dump(subject_queue, file, ensure_ascii=False, indent=2)
    return subject_queue


# === ENTITY LITERAL CHECK ===
def is_literal(o, path_config, main_config):
    main_config.prompt = (
        f'I want you to perform named entity recognition (NER) on '
        f'the topic of the {main_config.topic}. '
        f'Your task is to classify if a given phrase is a '
        f'topic-relevant named entity, or not.\n\n'
        f'- If the phrase is a named entity, return "false".\n'
        f'- If the phrase is not a named entity, return "true".\n'
        f'- Return only true or false.\n'
        f'Phrase: "{o}"'
    )
    response = prompt_llm_local(main_config)
    result = response.strip().lower()
    if result == 'true':
        append_to_jsonl_file(path_config.not_ne_path, {'text': o})
        return True
    return result != 'false'


def get_total_node_count(
        subject_queue, processed_subjects, triples_output_path
):
    processed = set(processed_subjects)
    queued = set(subject_queue)

    try:
        with open(triples_output_path, 'r', encoding='utf8') as f:
            for line in f:
                try:
                    triple = json.loads(line)
                    processed.add(triple.get("s", ""))
                    processed.add(triple.get("o", ""))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass

    return len(processed.union(queued))


def process_arguments(config: RunConfig):
    try:
        config.dir = Path(config.dir)
    except Exception as e:
        logger.error(f"Invalid directory path: {config.dir}. Error: {e}")
        return

    if not validators.url(config.url):
        logger.error(f"Invalid URL: {config.url}")
        return

    config.num_entities, config.end_time = None, None
    if config.termination_label == "Min Entities":
        config.num_entities = int(config.termination)
    elif config.termination_label == "Runtime (minutes)":
        config.end_time = time.time() + int(config.termination) * 60

    return config


def main(main_config: RunConfig):
    # === MAIN LOOP ===
    logger.info("==== Knowledge Extraction Pipeline Started ====")

    try:
        main_config = process_arguments(main_config)
    except Exception as e:
        logger.error(f"Failed to process arguments: {e}")
        return

    try:
        path_config = PathConfig(*define_file_paths(main_config.dir))
    except Exception as e:
        logger.error(f"Failed to set up file paths: {e}")
        return

    subject_queue = [main_config.seed_entity]  # seed entity
    processed_subjects = []  # initially empty
    for i in range(max_iterations):
        new_subjects_from_objects = []
        new_subjects = read_first_n_subjects(subject_queue, nthreads)

        if len(new_subjects) == 0:
            logger.info("No more subjects in queue. Exiting loop.")
            break

        threads = []
        result_queue = queue.Queue()
        error_queue = queue.Queue()

        # TODO: capping new subjects to terminate on exact number of
        # entities requested by user
        for subj in new_subjects:
            thread = threading.Thread(
                target=get_triples,
                args=(
                    subj, result_queue, error_queue,
                    path_config, main_config,
                )
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        if error_queue.empty():
            all_triples = []
            while not result_queue.empty():
                all_triples.extend(result_queue.get())

            store_triples(all_triples, path_config.triples_output_path)

            all_objects = [t.get('o', '') for t in all_triples]
            for o in all_objects:
                queues = (
                    processed_subjects,
                    new_subjects_from_objects,
                    subject_queue
                )
                if any(o in s for s in queues):
                    continue
                if is_literal(o, path_config, main_config):
                    continue
                new_subjects_from_objects.append(o)

            processed_subjects = append_to_processed_subjects(
                processed_subjects, new_subjects,
                path_config.processed_subjects_path
            )
            subject_queue = delete_first_n_subjects(subject_queue, nthreads)

            # total_nodes = getTotalNodeCount()
            # limit = 300
            # if total_nodes > limit:
            #     logger.warning(
            #         f"Node count exceeded limit "
            #         f"(current: {total_nodes}, limit: {limit}). "
            #         f"Stopping process."
            #     )
            #     break

            subject_queue = append_to_subject_queue(
                subject_queue, new_subjects_from_objects,
                path_config.subject_queue_path
            )
            append_to_jsonl_file(
                path_config.subject_queue_path, subject_queue
            )
            append_to_jsonl_file(
                path_config.processed_subjects_path, processed_subjects
            )

            if len(new_subjects_from_objects) == 0 and len(subject_queue) == 0:
                logger.info(
                    "No new subjects found and queue is now empty. Exiting."
                )
                break

            logger.info(f"Iteration {i} completed.")
            logger.info(
                f"Queue size: {len(subject_queue)}, "
                f"Processed: {len(processed_subjects)}"
            )
            logger.info(f"{time.strftime('%X %x %Z')}\n")
            if (
                main_config.num_entities is not None and
                len(processed_subjects) >= main_config.num_entities
            ):
                logger.info(
                    f"Reached target of {main_config.num_entities} processed entities. "
                    f"Stopping process."
                )
                break
            # Warning: This time-based termination is not exact, as threads will
            # only check the time condition after they finish processing current subject.
            if main_config.end_time is not None and time.time() >= main_config.end_time:
                logger.info(
                    f"Reached runtime limit of {main_config.termination} minutes. "
                    f"Stopping process."
                )
                break
            time.sleep(1)
        else:
            error_msg = str(error_queue.get())[:100]
            logger.error(f"Error in thread processing: {error_msg}")
            time.sleep(60)

    logger.info("==== Knowledge Extraction Pipeline Finished ====")


if __name__ == "__main__":
    main()
