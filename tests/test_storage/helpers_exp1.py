"""Direct-SQL fixtures for reader/writer tests (no writer under test)."""

import json
import sqlite3


def insert_call(
    conn: sqlite3.Connection,
    experiment_id: str,
    input_id: str,
    stage_index: int = 0,
    status: str = "success",
    latency: float = 0.1,
    usage: dict | None = None,
    call_id: str | None = None,
) -> str:
    call_id = call_id or f"{experiment_id}-{input_id}-{stage_index}"
    conn.execute(
        "INSERT INTO calls (call_id, experiment_id, input_id, stage_index, executor,"
        " question_count, latency, retry_count, token_usage_json, status,"
        " error_message, timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            call_id,
            experiment_id,
            input_id,
            stage_index,
            "JevStageExecutor",
            1,
            latency,
            None,
            json.dumps(usage) if usage else None,
            status,
            None,
            "t",
        ),
    )
    conn.commit()
    return call_id


def insert_judge_log(
    conn: sqlite3.Connection,
    experiment_id: str,
    input_id: str,
    judge_id: str,
    value: float | None = None,
    error: str | None = None,
    call_id: str = "c1",
    raw_p: float = 0.5,
) -> None:
    raw = json.dumps({"kind": "noul", "raw_value": raw_p, "raw_probability": raw_p})
    conn.execute(
        "INSERT INTO judge_logs (call_id, experiment_id, input_id, judge_id,"
        " judge_version, judge_prompt_or_definition, question_json, raw_answer_json,"
        " judge_latency, timestamp, interpreted_value, interpret_error)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            call_id,
            experiment_id,
            input_id,
            judge_id,
            "v",
            "d",
            "{}",
            raw,
            0.1,
            "t",
            value,
            error,
        ),
    )
    conn.commit()
