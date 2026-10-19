"""Offline fit / score / persist steps over stored raw answers (spec §6)."""

from __future__ import annotations

import sqlite3

from pydantic import BaseModel

from src.aggregation.core import (
    IsotonicCalibrator,
    MarginChoice,
    choose_margin,
    decide,
    margin_grid,
    mean_probability,
)
from src.data.schema import Sample
from src.experiments.config import Exp1Config
from src.metrics.core import Row
from src.storage.reader import completion_latency, load_calls, load_probabilities
from src.storage.writer import SqliteStorageWriter


class ArmFit(BaseModel):
    experiment_id: str
    n_expected: int
    calibrator: dict[str, list[float]]
    margins: dict[str, MarginChoice]  # keyed by Exp1Config.target_key


def raw_means(
    conn: sqlite3.Connection,
    experiment_id: str,
    n_expected: int,
    samples: list[Sample],
) -> dict[str, float | None]:
    """Mean P(HIGH) per sample; None when fewer than N valid answers."""
    probs = load_probabilities(conn, experiment_id)
    return {
        s.input_id: mean_probability(
            list(probs.get(s.input_id, {}).values()), n_expected
        )
        for s in samples
    }


async def fit_arm(
    conn: sqlite3.Connection,
    writer: SqliteStorageWriter,
    experiment_id: str,
    n_expected: int,
    calib: list[Sample],
    thresh: list[Sample],
    cfg: Exp1Config,
) -> ArmFit:
    """Fit the calibrator on `calib`, choose margins on `thresh`, freeze both."""
    means = raw_means(conn, experiment_id, n_expected, calib)
    pairs = [
        (means[s.input_id], 1.0 if s.label == "HIGH" else 0.0)
        for s in calib
        if means[s.input_id] is not None
    ]
    calibrator = IsotonicCalibrator.fit([p for p, _ in pairs], [y for _, y in pairs])
    thresh_means = raw_means(conn, experiment_id, n_expected, thresh)
    thresh_ps = [calibrator.predict(m) for m in thresh_means.values() if m is not None]
    grid = margin_grid(cfg.margin_step)
    fit = ArmFit(
        experiment_id=experiment_id,
        n_expected=n_expected,
        calibrator=calibrator.to_dict(),
        margins={
            cfg.target_key(t): choose_margin(thresh_ps, t, grid)
            for t in cfg.coverage_targets
        },
    )
    await writer.freeze_config(experiment_id, "fit", fit.model_dump())
    return fit


def score_rows(
    conn: sqlite3.Connection, fit: ArmFit, samples: list[Sample]
) -> list[Row]:
    """Apply the frozen calibrator; invalid samples keep `p = None`."""
    calibrator = IsotonicCalibrator.from_dict(fit.calibrator)
    means = raw_means(conn, fit.experiment_id, fit.n_expected, samples)
    rows = []
    for s in samples:
        mean = means[s.input_id]
        rows.append(
            Row(
                input_id=s.input_id,
                regime=s.regime,
                label=s.label,
                t_index=s.t_index,
                p=None if mean is None else calibrator.predict(mean),
            )
        )
    return rows


async def write_decisions(
    conn: sqlite3.Connection,
    writer: SqliteStorageWriter,
    fit: ArmFit,
    rows: list[Row],
    margin: float,
) -> None:
    """Persist the headline operating point into `decisions` and `was_used`.

    Valid replicas of an invalid sample get `was_used = 0` (spec §8). Other
    coverage targets live only in derived reports.
    """
    probs = load_probabilities(conn, fit.experiment_id)
    latency = completion_latency(load_calls(conn, fit.experiment_id))
    for row in rows:
        await writer.mark_used(
            fit.experiment_id,
            row.input_id,
            list(probs.get(row.input_id, {})),
            row.p is not None,
        )
        if row.p is None:
            continue
        decision = decide(row.p, margin)
        await writer.record_decision(
            experiment_id=fit.experiment_id,
            input_id=row.input_id,
            aggregate_score=row.p,
            final_confidence=abs(row.p - 0.5) + 0.5,
            final_decision=decision,
            is_correct=None if decision == "SKIP" else int(decision == row.label),
            total_latency=latency.get(row.input_id),
            early_stopped=0,
        )
