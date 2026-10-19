"""StorageWriter implementation backed by sqlite3.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §3, §5.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

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

    async def record_experiment(
        self,
        experiment_id: str,
        config: dict[str, Any],
        aggregator_version: str | None = None,
    ) -> None:
        """Create the experiment row; a no-op when it already exists, so
        resumed runs keep the original configuration."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT OR IGNORE INTO experiments"
                    " (experiment_id, config_json, aggregator_version, created_at)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        experiment_id,
                        json.dumps(config, sort_keys=True),
                        aggregator_version,
                        now,
                    ),
                )

    async def freeze_config(self, experiment_id: str, key: str, value: Any) -> None:
        """Write `value` under `config_json["frozen"][key]`; never overwrite."""
        async with self._lock:
            with self._conn:
                row = self._conn.execute(
                    "SELECT config_json FROM experiments WHERE experiment_id = ?",
                    (experiment_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(experiment_id)
                config = json.loads(row[0])
                frozen = config.setdefault("frozen", {})
                if key in frozen:
                    raise ValueError(f"{key!r} already frozen for {experiment_id}")
                frozen[key] = value
                self._conn.execute(
                    "UPDATE experiments SET config_json = ? WHERE experiment_id = ?",
                    (json.dumps(config, sort_keys=True), experiment_id),
                )

    async def record_input(
        self,
        input_id: str,
        features: dict[str, Any],
        ground_truth: str | None,
        task_type: str = "high_low",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT OR IGNORE INTO inputs"
                    " (input_id, task_type, input_features_json, ground_truth,"
                    " created_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        input_id,
                        task_type,
                        json.dumps(features, sort_keys=True),
                        ground_truth,
                        now,
                    ),
                )

    async def record_decision(
        self,
        *,
        experiment_id: str,
        input_id: str,
        aggregate_score: float | None,
        final_confidence: float | None,
        final_decision: str | None,
        is_correct: int | None,
        total_latency: float | None,
        early_stopped: int | None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO decisions (experiment_id, input_id,"
                    " aggregate_score, final_confidence, final_decision, is_correct,"
                    " total_latency, early_stopped, timestamp)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        experiment_id,
                        input_id,
                        aggregate_score,
                        final_confidence,
                        final_decision,
                        is_correct,
                        total_latency,
                        early_stopped,
                        now,
                    ),
                )

    async def mark_used(
        self, experiment_id: str, input_id: str, judge_ids: list[str], used: bool
    ) -> None:
        """Set `was_used` for the named judges of one input (spec §8)."""
        if not judge_ids:
            return
        placeholders = ",".join("?" for _ in judge_ids)
        async with self._lock:
            with self._conn:
                self._conn.execute(
                    "UPDATE judge_logs SET was_used = ? WHERE experiment_id = ?"
                    f" AND input_id = ? AND judge_id IN ({placeholders})",
                    (int(used), experiment_id, input_id, *judge_ids),
                )
