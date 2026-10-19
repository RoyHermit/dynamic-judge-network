"""Reader helpers (spec §8, §9.1)."""

import math

import pytest
from helpers_exp1 import insert_call, insert_judge_log

from src.storage import db
from src.storage.reader import (
    CallRow,
    completed_units,
    completion_latency,
    load_calls,
    load_probabilities,
    pending_interpretations,
)


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "t.db")


def test_completed_units_include_error_calls(conn):
    insert_call(conn, "e1", "i1", 0)
    insert_call(conn, "e1", "i2", 1, status="error")
    insert_call(conn, "other", "i9", 0)
    assert completed_units(conn, "e1") == {("i1", 0), ("i2", 1)}


def test_load_probabilities_skips_errors_missing_and_out_of_range(conn):
    insert_judge_log(conn, "e1", "i1", "hl_judge#0", value=0.7)
    insert_judge_log(conn, "e1", "i1", "hl_judge#1", error="boom")
    insert_judge_log(conn, "e1", "i1", "hl_judge#2", value=None)
    insert_judge_log(conn, "e1", "i1", "hl_judge#3", value=1.5)
    insert_judge_log(conn, "e1", "i1", "hl_judge#4", value=math.nan)
    assert load_probabilities(conn, "e1") == {"i1": {"hl_judge#0": 0.7}}


def test_pending_interpretations_returns_uninterpreted_rows_only(conn):
    insert_judge_log(conn, "e1", "i1", "hl_judge#0", value=None, raw_p=0.8)
    insert_judge_log(conn, "e1", "i1", "hl_judge#1", value=0.7)
    insert_judge_log(conn, "e1", "i1", "hl_judge#2", error="x")
    pending = pending_interpretations(conn, "e1")
    assert [(c, j) for c, j, _ in pending] == [("c1", "hl_judge#0")]
    assert pending[0][2].raw_probability == 0.8


def test_load_calls_and_completion_latency(conn):
    insert_call(conn, "e1", "i1", 0, latency=0.25, usage={"input_tokens": 4})
    insert_call(conn, "e1", "i1", 1, latency=0.5)
    calls = load_calls(conn, "e1")
    assert isinstance(calls[0], CallRow)
    assert completion_latency(calls) == {"i1": 0.75}
