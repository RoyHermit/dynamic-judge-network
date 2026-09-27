"""Integration tests for SqliteStorageWriter against a real sqlite3 file.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §5, §8.
"""

import sqlite3

import pytest

from src.judges.interface import Answer, CallRecord, Decision, Question, RawJudgeRecord
from src.storage import db
from src.storage.writer import SqliteStorageWriter


def _make_call(call_id: str = "c1", status: str = "success") -> CallRecord:
    return CallRecord(
        call_id=call_id,
        experiment_id="e1",
        input_id="i1",
        stage_index=0,
        executor="JevStageExecutor",
        question_count=1,
        latency=0.05,
        retry_count=None,
        token_usage=None,
        status=status,
        error_message=None if status == "success" else "boom",
    )


def _make_raw_record(judge_id: str = "j1") -> RawJudgeRecord:
    return RawJudgeRecord(
        judge_id=judge_id,
        judge_version="1.0",
        judge_prompt_or_definition="test judge",
        question=Question(kind="choice", prompt="pick", options=["HIGH", "LOW"]),
        raw_answer=Answer(kind="choice", raw_value="HIGH", raw_probability=0.8),
        latency=0.05,
    )


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


async def test_record_call_then_interpretation_lands_in_right_columns(conn):
    writer = SqliteStorageWriter(conn)
    call = _make_call()
    await writer.record_call(call, [_make_raw_record()])
    await writer.record_interpretation(
        call_id=call.call_id,
        judge_id="j1",
        decision=Decision(value="HIGH", confidence=0.8),
        error=None,
    )

    row = conn.execute(
        "SELECT interpreted_value, interpreted_confidence, interpret_error "
        "FROM judge_logs WHERE call_id = ? AND judge_id = ?",
        (call.call_id, "j1"),
    ).fetchone()

    assert row[0] == "HIGH"
    assert row[1] == 0.8
    assert row[2] is None


async def test_record_interpretation_error_leaves_value_columns_null(conn):
    writer = SqliteStorageWriter(conn)
    call = _make_call()
    await writer.record_call(call, [_make_raw_record()])

    await writer.record_interpretation(
        call_id=call.call_id, judge_id="j1", decision=None, error="interpret blew up"
    )

    row = conn.execute(
        "SELECT interpreted_value, interpreted_confidence, evidence, interpret_error "
        "FROM judge_logs WHERE call_id = ? AND judge_id = ?",
        (call.call_id, "j1"),
    ).fetchone()
    assert row[0] is None
    assert row[1] is None
    assert row[2] is None
    assert row[3] == "interpret blew up"


async def test_record_interpretation_rejects_both_decision_and_error(conn):
    writer = SqliteStorageWriter(conn)
    call = _make_call()
    await writer.record_call(call, [_make_raw_record()])

    with pytest.raises(ValueError):
        await writer.record_interpretation(
            call_id=call.call_id,
            judge_id="j1",
            decision=Decision(value="HIGH"),
            error="also this",
        )


async def test_record_interpretation_rejects_neither_decision_nor_error(conn):
    writer = SqliteStorageWriter(conn)
    call = _make_call()
    await writer.record_call(call, [_make_raw_record()])

    with pytest.raises(ValueError):
        await writer.record_interpretation(
            call_id=call.call_id, judge_id="j1", decision=None, error=None
        )


async def test_failed_call_writes_calls_row_with_zero_judge_logs(conn):
    writer = SqliteStorageWriter(conn)
    call = _make_call(status="error")

    await writer.record_call(call, [])

    calls_row = conn.execute(
        "SELECT status, error_message FROM calls WHERE call_id = ?", (call.call_id,)
    ).fetchone()
    assert calls_row == ("error", "boom")

    logs_count = conn.execute(
        "SELECT COUNT(*) FROM judge_logs WHERE call_id = ?", (call.call_id,)
    ).fetchone()[0]
    assert logs_count == 0


async def test_count_judge_logs_id_is_zero_not_one_for_left_join_with_no_logs(conn):
    """Pins the §5 off-by-one: COUNT(*) over a LEFT JOIN counts the
    all-NULL row; COUNT(judge_logs.id) does not."""
    writer = SqliteStorageWriter(conn)
    call = _make_call(status="error")
    await writer.record_call(call, [])
    conn.execute(
        "INSERT INTO decisions (experiment_id, input_id, timestamp) VALUES (?, ?, ?)",
        ("e1", "i1", "2026-09-27T00:00:00+00:00"),
    )
    conn.commit()

    row = conn.execute(
        """
        SELECT COUNT(*) AS star_count, COUNT(judge_logs.id) AS id_count
        FROM decisions
        LEFT JOIN judge_logs
          ON judge_logs.experiment_id = decisions.experiment_id
         AND judge_logs.input_id = decisions.input_id
        WHERE decisions.experiment_id = ? AND decisions.input_id = ?
        """,
        ("e1", "i1"),
    ).fetchone()

    assert row[0] == 1  # the naive, wrong count
    assert row[1] == 0  # the correct count


async def test_unique_call_id_judge_id_prevents_duplicate_judge_logs_row(conn):
    writer = SqliteStorageWriter(conn)
    call = _make_call()

    with pytest.raises(sqlite3.IntegrityError):
        await writer.record_call(call, [_make_raw_record("j1"), _make_raw_record("j1")])


async def test_failed_record_call_is_rolled_back_not_committed_by_next_write(conn):
    """A failed record_call must roll back its partial transaction, otherwise
    the next write's commit would silently persist the half-written batch."""
    writer = SqliteStorageWriter(conn)
    failed_call = _make_call("failed")

    with pytest.raises(sqlite3.IntegrityError):
        await writer.record_call(
            failed_call, [_make_raw_record("j1"), _make_raw_record("j1")]
        )

    ok_call = _make_call("ok")
    await writer.record_call(ok_call, [_make_raw_record("j1")])

    call_ids = {row[0] for row in conn.execute("SELECT call_id FROM calls")}
    assert call_ids == {"ok"}
    failed_logs = conn.execute(
        "SELECT COUNT(*) FROM judge_logs WHERE call_id = ?", ("failed",)
    ).fetchone()[0]
    assert failed_logs == 0
