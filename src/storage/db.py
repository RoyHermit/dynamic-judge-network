"""SQLite connection handling and schema initialization.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §5.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    config_json TEXT NOT NULL,
    aggregator_version TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inputs (
    input_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    input_features_json TEXT NOT NULL,
    ground_truth TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calls (
    call_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    input_id TEXT NOT NULL,
    stage_index INTEGER NOT NULL,
    executor TEXT NOT NULL,
    question_count INTEGER NOT NULL,
    latency REAL NOT NULL,
    retry_count INTEGER,
    token_usage_json TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS judge_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    input_id TEXT NOT NULL,
    judge_id TEXT NOT NULL,
    judge_version TEXT NOT NULL,
    judge_prompt_or_definition TEXT NOT NULL,
    question_json TEXT NOT NULL,
    raw_answer_json TEXT NOT NULL,
    judge_latency REAL NOT NULL,
    timestamp TEXT NOT NULL,
    interpreted_value,
    interpreted_confidence REAL,
    evidence TEXT,
    interpret_error TEXT,
    was_used INTEGER,
    activation_source TEXT,
    activation_reason TEXT,
    graph_depth INTEGER,
    parent_judge TEXT,
    UNIQUE(call_id, judge_id)
);

CREATE TABLE IF NOT EXISTS decisions (
    experiment_id TEXT NOT NULL,
    input_id TEXT NOT NULL,
    aggregate_score REAL,
    final_confidence REAL,
    final_decision TEXT,
    is_correct INTEGER,
    total_latency REAL,
    early_stopped INTEGER,
    timestamp TEXT NOT NULL,
    PRIMARY KEY (experiment_id, input_id)
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection with WAL mode enabled and ensure the schema exists.

    Safe to call repeatedly against the same file (CREATE TABLE IF NOT
    EXISTS) — this is the only place the schema is defined.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
