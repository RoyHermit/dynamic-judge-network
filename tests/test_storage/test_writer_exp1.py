"""Experiment 1 writer extensions (spec §3.2, §8)."""

import json

import pytest
from helpers_exp1 import insert_judge_log

from src.storage import db
from src.storage.writer import SqliteStorageWriter


@pytest.fixture
def env(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    return conn, SqliteStorageWriter(conn)


async def test_record_experiment_is_idempotent(env):
    conn, writer = env
    await writer.record_experiment("e1", {"a": 1})
    await writer.record_experiment("e1", {"a": 2})
    rows = conn.execute("SELECT config_json FROM experiments").fetchall()
    assert len(rows) == 1 and json.loads(rows[0][0]) == {"a": 1}


async def test_load_experiment_config_returns_stored_config(env):
    conn, writer = env
    await writer.record_experiment("e1", {"a": 1})
    from src.storage.reader import load_experiment_config

    assert load_experiment_config(conn, "e1") == {"a": 1}
    assert load_experiment_config(conn, "missing") is None


async def test_freeze_config_merges_and_refuses_overwrite(env):
    conn, writer = env
    await writer.record_experiment("e1", {"a": 1})
    await writer.freeze_config("e1", "fit", {"m": 0.1})
    cfg = json.loads(conn.execute("SELECT config_json FROM experiments").fetchone()[0])
    assert cfg["a"] == 1 and cfg["frozen"]["fit"] == {"m": 0.1}
    with pytest.raises(ValueError):
        await writer.freeze_config("e1", "fit", {"m": 0.2})
    with pytest.raises(KeyError):
        await writer.freeze_config("missing", "fit", {})


async def test_record_input_is_idempotent_and_stores_truth(env):
    conn, writer = env
    await writer.record_input("i1", {"state": {"bars": [1.0]}}, "HIGH")
    await writer.record_input("i1", {"state": {"bars": [9.0]}}, "LOW")
    rows = conn.execute("SELECT task_type, ground_truth FROM inputs").fetchall()
    assert rows == [("high_low", "HIGH")]


async def test_record_decision_and_mark_used(env):
    conn, writer = env
    await writer.record_decision(
        experiment_id="e1",
        input_id="i1",
        aggregate_score=0.7,
        final_confidence=0.7,
        final_decision="HIGH",
        is_correct=1,
        total_latency=0.5,
        early_stopped=0,
    )
    rows = conn.execute("SELECT final_decision, is_correct FROM decisions").fetchall()
    assert rows == [("HIGH", 1)]

    insert_judge_log(conn, "e1", "i1", "hl_judge#0", 0.7)
    insert_judge_log(conn, "e1", "i1", "hl_judge#1", 0.6)
    await writer.mark_used("e1", "i1", ["hl_judge#0"], True)
    used = dict(conn.execute("SELECT judge_id, was_used FROM judge_logs").fetchall())
    assert used["hl_judge#0"] == 1 and used["hl_judge#1"] is None
