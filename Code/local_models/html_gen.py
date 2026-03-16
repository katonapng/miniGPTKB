import csv
import os
import sqlite3
import time
import urllib.parse
from collections import Counter

import numpy as np
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF

from Code.local_models.logger_setup import logger


MAX_RETRIES = 100
RETRY_SLEEP = 2


def get_triples_db(db_file):
    query = "SELECT subject, predicate, object FROM triple;"
    for attempt in range(1, MAX_RETRIES + 1):
        db = f'file:{db_file}?mode=ro'
        try:
            with sqlite3.connect(db, uri=True, timeout=30) as conn:
                cur = conn.cursor()
                cur.execute(query)
                return set(cur.fetchall())
        except sqlite3.DatabaseError as e:
            logger.info(f"[{db_file}] attempt {attempt} failed: {e}")
            time.sleep(RETRY_SLEEP)
    return set()


def get_node_types(db_file):
    types = {}
    query = "SELECT name, type FROM node;"
    try:
        with sqlite3.connect(f'file:{db_file}?mode=ro', uri=True) as conn:
            cur = conn.cursor()
            cur.execute(query)
            for name, ntype in cur.fetchall():
                if name in types:
                    if types[name] != "instance" and ntype == "instance":
                        types[name] = "instance"
                else:
                    types[name] = ntype
    except sqlite3.DatabaseError:
        pass
    return types


def safe_name(name):
    cleaned = name.strip().replace(" ", "_")
    return urllib.parse.quote(cleaned, safe="_")


def get_html(topic):
    # ---------- CONFIG ----------
    # could be multiple files if you have multiple runs
    db_files = [
        f"./{topic}GPTKB.db"
    ]

    base_dir = f"./{topic}GPTKB"  # name of the directory
    output_base = os.path.join(base_dir, f"{topic}GPTKB")
    os.makedirs(base_dir, exist_ok=True)

    triple_sets = []
    for db_file in db_files:
        if os.path.exists(db_file):
            triple_sets.append(get_triples_db(db_file))
        else:
            logger.info(f"Missing DB: {db_file}")
            triple_sets.append(set())

    num_runs = len(triple_sets)

    node_types_all = {}
    for db_file in db_files:
        if os.path.exists(db_file):
            local = get_node_types(db_file)
            for n, t in local.items():
                if n in node_types_all:
                    if node_types_all[n] != "instance" and t == "instance":
                        node_types_all[n] = "instance"
                else:
                    node_types_all[n] = t

    # ---------- STEP 3: Count triple frequency ----------
    triple_counts = Counter()
    for s in triple_sets:
        for triple in s:
            triple_counts[triple] += 1

    # ---------- STEP 4: Elbow detection ----------
    threshold_results = {}

    if num_runs >= 3:
        for X in range(1, num_runs + 1):
            threshold_results[X] = sum(1 for c in triple_counts.values() if c >= X)

        X_vals = np.array(list(threshold_results.keys()))
        Y_vals = np.array(list(threshold_results.values()))

        line_vec = np.array([X_vals[-1] - X_vals[0], Y_vals[-1] - Y_vals[0]])
        norm = np.linalg.norm(line_vec)

        if norm == 0:
            auto_X = 1
        else:
            line_vec = line_vec / norm
            distances = []
            for i in range(len(X_vals)):
                point_vec = np.array([X_vals[i] - X_vals[0], Y_vals[i] - Y_vals[0]])
                proj = np.dot(point_vec, line_vec) * line_vec
                distances.append(np.linalg.norm(point_vec - proj))
            auto_X = X_vals[np.argmax(distances)]

    else:
        auto_X = 1
        logger.info("Elbow skipped (less than 3 runs)")

    final_triples = [t for t, c in triple_counts.items() if c >= auto_X]
    logger.info(f"Final triples: {len(final_triples)}")

    # ---------- STEP 5: Restrict nodes ----------
    used_nodes = (
        {s for s, _, _ in final_triples} | {o for _, _, o in final_triples}
    )

    final_node_types = {
        n: node_types_all.get(n, "literal") for n in used_nodes
    }

    # ---------- STEP 6: Save SQLite ----------
    output_db = output_base + ".db"
    if os.path.exists(output_db):
        os.remove(output_db)

    with sqlite3.connect(output_db) as conn:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE triple (subject TEXT, predicate TEXT, object TEXT)"
        )
        cur.executemany("INSERT INTO triple VALUES (?, ?, ?)", final_triples)

        cur.execute("CREATE TABLE node (name TEXT, type TEXT)")
        cur.executemany(
            "INSERT INTO node VALUES (?, ?)", final_node_types.items()
        )

        cur.execute("CREATE TABLE predicate (name TEXT)")
        cur.executemany(
            "INSERT INTO predicate VALUES (?)",
            [(p,) for p in sorted({p for _, p, _ in final_triples})]
        )
        conn.commit()

    # ---------- STEP 7: Save CSV ----------
    output_csv = output_base + ".csv"
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["subject", "predicate", "object"])
        writer.writerows(final_triples)

    # ---------- STEP 8: Save TTL with rdf:type ----------
    output_ttl = output_base + ".ttl"
    g = Graph()
    EX = Namespace("http://minigptkb/")

    def safe_name(name):
        cleaned = name.strip().replace(" ", "_")
        return urllib.parse.quote(cleaned, safe="_")

    for s, p, o in final_triples:
        subj = URIRef(EX[safe_name(s)])
        pred = URIRef(EX[safe_name(p)])

        if final_node_types.get(s) == "instance":
            g.add((subj, RDF.type, EX.Instance))

        if final_node_types.get(o) == "instance":
            obj = URIRef(EX[safe_name(o)])
        else:
            obj = Literal(o)

        g.add((subj, pred, obj))

    g.serialize(destination=output_ttl, format="turtle")

    # ---------- STEP 9: Basic statistics ----------
    logger.info("\nKB Statistics:")
    logger.info("Entities:", len(used_nodes))
    logger.info("Predicates:", len(set(p for _, p, _ in final_triples)))
    logger.info("Triples:", len(final_triples))


def main():
    topic = "Ancient Babylon"
    get_html(topic)


if __name__ == "__main__":
    main()
