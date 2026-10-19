"""Resumable arm runner for A and C (spec §5.3, §9.1)."""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Any, Literal

from pydantic import BaseModel

from src.data.schema import Sample
from src.data.synthetic import same_dataset
from src.judges.definitions.high_low import HighLowJudge, replica_index
from src.judges.interface import JudgeExecutor
from src.storage.reader import (
    completed_units,
    load_experiment_config,
    pending_interpretations,
)
from src.storage.writer import SqliteStorageWriter


class ArmSpec(BaseModel):
    study_id: str
    arm: Literal["A", "C"]
    topology: Literal["batched", "separate"] = "batched"
    run: int = 1
    n_replicas: int = 5
    horizon: int = 5

    @property
    def experiment_id(self) -> str:
        if self.arm == "A":
            return f"{self.study_id}-A-run{self.run}"
        return f"{self.study_id}-C-{self.topology}"

    def units(self) -> list[tuple[int, list[HighLowJudge]]]:
        """(stage_index, judges) execution units for one sample."""
        if self.arm == "A":
            return [(0, [HighLowJudge(self.horizon)])]
        replicas = [HighLowJudge(self.horizon, k) for k in range(self.n_replicas)]
        if self.topology == "batched":
            return [(0, replicas)]
        return [(k, [judge]) for k, judge in enumerate(replicas)]


# Keys that define what a stored answer means; resuming with different values
# would pair old answers with a new dataset or model (spec §9.1).
_IDENTITY_KEYS = ("data", "requested_model", "extra_body", "n_replicas", "horizon")


def _check_identity(
    conn: sqlite3.Connection, experiment_id: str, config: dict[str, Any]
) -> None:
    stored = load_experiment_config(conn, experiment_id) or {}
    for key in _IDENTITY_KEYS:
        if key not in config or key not in stored:
            continue
        # `data` is compared by generated-dataset identity, not dict equality
        same = (
            same_dataset(stored[key], config[key])
            if key == "data"
            else stored[key] == config[key]
        )
        if not same:
            raise ValueError(
                f"experiment {experiment_id!r} was created with a different "
                f"{key!r}; use another study_id instead of resuming"
            )


class _Budget:
    def __init__(self, limit: int | None) -> None:
        self._limit = limit
        self.used = 0

    def take(self) -> bool:
        if self._limit is not None and self.used >= self._limit:
            return False
        self.used += 1
        return True


async def finish_pending_interpretations(
    conn: sqlite3.Connection, writer: SqliteStorageWriter, spec: ArmSpec
) -> None:
    """Re-interpret stored raw answers left without a result (no API call)."""
    for call_id, judge_id, answer in pending_interpretations(conn, spec.experiment_id):
        judge = HighLowJudge(spec.horizon, replica_index(judge_id))
        try:
            decision = judge.interpret(answer)
        except Exception as exc:  # noqa: BLE001 - recorded, never re-raised
            await writer.record_interpretation(call_id, judge_id, None, str(exc))
            continue
        await writer.record_interpretation(call_id, judge_id, decision, None)


async def run_arm(
    spec: ArmSpec,
    samples: list[Sample],
    executor: JudgeExecutor,
    writer: SqliteStorageWriter,
    conn: sqlite3.Connection,
    *,
    config_extra: dict[str, Any] | None = None,
    sample_concurrency: int = 1,
    max_units: int | None = None,
) -> int:
    """Run every incomplete unit of `spec` over `samples`; return units run.

    A unit is complete when a call for `(input_id, stage_index)` is stored,
    whatever its status; failed calls and dropped answers are never retried
    (spec §9.1). Replicas of one sample run sequentially, so completion
    time is the sum of call latencies.
    """
    config = {
        **spec.model_dump(),
        "dispatch": {
            "sample_concurrency": sample_concurrency,
            "replica_dispatch": "sequential",
        },
        **(config_extra or {}),
    }
    await writer.record_experiment(spec.experiment_id, config)
    _check_identity(conn, spec.experiment_id, config)
    await finish_pending_interpretations(conn, writer, spec)
    done = completed_units(conn, spec.experiment_id)
    budget = _Budget(max_units)
    semaphore = asyncio.Semaphore(sample_concurrency)

    async def run_sample(sample: Sample) -> None:
        async with semaphore:
            await writer.record_input(
                sample.input_id,
                {
                    "state": sample.state,
                    "regime": sample.regime,
                    "split": sample.split,
                    "t_index": sample.t_index,
                },
                sample.label,
            )
            for stage_index, judges in spec.units():
                if (sample.input_id, stage_index) in done:
                    continue
                if not budget.take():
                    return
                await executor.run_stage(
                    sample.state,
                    judges,
                    experiment_id=spec.experiment_id,
                    input_id=sample.input_id,
                    stage_index=stage_index,
                )

    await asyncio.gather(*(run_sample(s) for s in samples))
    return budget.used
