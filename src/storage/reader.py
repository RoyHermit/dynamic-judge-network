"""Read helpers over the Experiment 1 sqlite tables (spec §8, §9.1)."""

from __future__ import annotations

import json
import sqlite3

from pydantic import BaseModel

from src.judges.interface import Answer


class CallRow(BaseModel):
    input_id: str
    stage_index: int
    latency: float
    status: str
    token_usage: dict | None = None


def completed_units(
    conn: sqlite3.Connection, experiment_id: str
) -> set[tuple[str, int]]:
    """(input_id, stage_index) pairs with a recorded call, success or error."""
    rows = conn.execute(
        "SELECT input_id, stage_index FROM calls WHERE experiment_id = ?",
        (experiment_id,),
    )
    return {(input_id, stage) for input_id, stage in rows}


def load_probabilities(
    conn: sqlite3.Connection, experiment_id: str
) -> dict[str, dict[str, float]]:
    """input_id -> judge_id -> valid P(HIGH).

    Rows with an interpret error, a missing value, or a value outside
    [0, 1] (including NaN) are omitted, never repaired (spec §9).
    """
    out: dict[str, dict[str, float]] = {}
    rows = conn.execute(
        "SELECT input_id, judge_id, interpreted_value, interpret_error"
        " FROM judge_logs WHERE experiment_id = ?",
        (experiment_id,),
    )
    for input_id, judge_id, value, error in rows:
        if error is not None or value is None:
            continue
        try:
            p = float(value)
        except (TypeError, ValueError):
            continue
        if not 0.0 <= p <= 1.0:  # False for NaN as well
            continue
        out.setdefault(input_id, {})[judge_id] = p
    return out


def load_calls(conn: sqlite3.Connection, experiment_id: str) -> list[CallRow]:
    rows = conn.execute(
        "SELECT input_id, stage_index, latency, status, token_usage_json"
        " FROM calls WHERE experiment_id = ? ORDER BY input_id, stage_index",
        (experiment_id,),
    )
    return [
        CallRow(
            input_id=i,
            stage_index=s,
            latency=lat,
            status=st,
            token_usage=json.loads(usage) if usage else None,
        )
        for i, s, lat, st, usage in rows
    ]


def pending_interpretations(
    conn: sqlite3.Connection, experiment_id: str
) -> list[tuple[str, str, Answer]]:
    """Stored raw answers that have neither a value nor an interpret error."""
    rows = conn.execute(
        "SELECT call_id, judge_id, raw_answer_json FROM judge_logs"
        " WHERE experiment_id = ? AND interpreted_value IS NULL"
        " AND interpret_error IS NULL",
        (experiment_id,),
    )
    return [(c, j, Answer.model_validate_json(raw)) for c, j, raw in rows]


def completion_latency(calls: list[CallRow]) -> dict[str, float]:
    """Per-input ensemble completion time under sequential dispatch.

    The runner dispatches the replicas of one sample sequentially, so the
    completion time is the sum of that input's call latencies (spec §7).
    Never sum `judge_logs.judge_latency`: it repeats the request latency.
    """
    out: dict[str, float] = {}
    for call in calls:
        out[call.input_id] = out.get(call.input_id, 0.0) + call.latency
    return out
