from dataclasses import dataclass
from typing import Optional


@dataclass
@dataclass
class RunConfig:
    dir: Optional[str] = None
    url: Optional[str] = None
    model: Optional[str] = None
    topic: Optional[str] = None
    prompt: Optional[str] = None
    seed_entity: Optional[str] = None
    min_triples: Optional[int] = None
    max_triples: Optional[int] = None
    termination_label: Optional[str] = None
    termination: Optional[int] = None
    num_entities: Optional[int] = None
    end_time: Optional[float] = None


@dataclass
class PathConfig:
    subject_queue_path: str
    processed_subjects_path: str
    triples_output_path: str
    parse_errors_path: str
    not_ne_path: str
