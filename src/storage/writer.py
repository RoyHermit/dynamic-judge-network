"""StorageWriter implementation backed by sqlite3.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §3, §5.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone

from src.judges.interface import CallRecord, Decision, RawJudgeRecord


class SqliteStorageWriter:
    """Serializes all writes through one connection + asyncio.Lock — §5
    notes sqlite3 connections are not safe to share across concurrent
    async tasks without external serialization."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = asyncio.Lock()

    async def record_call(
        self, call: CallRecord, raw_judge_records: list[RawJudgeRecord]
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            with self._conn:  # commits on success, rolls back on error
                self._conn.execute(
                    """
                    INSERT INTO calls (
                        call_id, experiment_id, input_id, stage_index, executor,
                        question_count, latency, retry_count, token_usage_json,
                        status, error_message, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        call.call_id,
                        call.experiment_id,
                        call.input_id,
                        call.stage_index,
                        call.executor,
                        call.question_count,
                        call.latency,
                        call.retry_count,
                        (
                            json.dumps(call.token_usage)
                            if call.token_usage is not None
                            else None
                        ),
                        call.status,
                        call.error_message,
                        now,
                    ),
                )
                for record in raw_judge_records:
                    self._conn.execute(
                        """
                        INSERT INTO judge_logs (
                            call_id, experiment_id, input_id, judge_id, judge_version,
                            judge_prompt_or_definition, question_json, raw_answer_json,
                            judge_latency, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            call.call_id,
                            call.experiment_id,
                            call.input_id,
                            record.judge_id,
                            record.judge_version,
                            record.judge_prompt_or_definition,
                            record.question.model_dump_json(),
                            record.raw_answer.model_dump_json(),
                            record.latency,
                            now,
                        ),
                    )

    async def record_interpretation(
        self,
        call_id: str,
        judge_id: str,
        decision: Decision | None,
        error: str | None,
    ) -> None:
        if (decision is None) == (error is None):
            raise ValueError("exactly one of decision or error must be set")
        async with self._lock:
            with self._conn:  # commits on success, rolls back on error
                self._conn.execute(
                    """
                    UPDATE judge_logs
                    SET interpreted_value = ?,
                        interpreted_confidence = ?,
                        evidence = ?,
                        interpret_error = ?
                    WHERE call_id = ? AND judge_id = ?
                    """,
                    (
                        decision.value if decision is not None else None,
                        decision.confidence if decision is not None else None,
                        decision.evidence if decision is not None else None,
                        error,
                        call_id,
                        judge_id,
                    ),
                )
