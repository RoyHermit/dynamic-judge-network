"""Experiment 2 offline fit / score steps: Platt primary, isotonic sensitivity."""

from __future__ import annotations

import sqlite3
from typing import Literal

from pydantic import BaseModel

from src.aggregation.core import (
    IsotonicCalibrator,
    MarginChoice,
    choose_margin,
    margin_grid,
    mean_probability,
)
from src.aggregation.platt import PlattCalibrator
from src.data.schema import Sample
from src.experiments.exp2_config import Exp2Config
from src.metrics.core import Row
from src.storage.reader import load_probabilities
from src.storage.writer import SqliteStorageWriter


class Exp2Fit(BaseModel):
    """Frozen calibration state for one arm."""

    experiment_id: str
    n_expected: int
    exclude_judges: list[str]
    platt: PlattCalibrator
    isotonic: dict[str, list[float]]  # sensitivity analysis only
    margins: dict[str, MarginChoice]  # chosen on thresh from Platt-calibrated p
    degenerate: bool = False


def subset_means(
    conn: sqlite3.Connection,
    experiment_id: str,
    n_expected: int,
    samples: list[Sample],
    exclude_judges: frozenset[str] = frozenset(),
) -> dict[str, float | None]:
    """Mean P(HIGH) over valid answers of non-excluded judges.

    None unless exactly `n_expected` valid answers remain after exclusion.
    """
    probs = load_probabilities(conn, experiment_id)
    return {
        s.input_id: mean_probability(
            [
                p
                for j, p in probs.get(s.input_id, {}).items()
                if j not in exclude_judges
            ],
            n_expected,
        )
        for s in samples
    }


def _build_fit(
    conn: sqlite3.Connection,
    experiment_id: str,
    n_expected: int,
    calib: list[Sample],
    thresh: list[Sample],
    cfg: Exp2Config,
    exclude_judges: frozenset[str],
) -> Exp2Fit:
    """Shared fit logic: Platt on calib, margins on thresh (no side effects)."""
    means = subset_means(conn, experiment_id, n_expected, calib, exclude_judges)
    pairs = [
        (means[s.input_id], 1.0 if s.label == "HIGH" else 0.0)
        for s in calib
        if means[s.input_id] is not None
    ]
    ps = [p for p, _ in pairs]
    ys = [y for _, y in pairs]
    platt = PlattCalibrator.fit(ps, ys, cfg.platt_l2)
    isotonic = (
        IsotonicCalibrator.fit(ps, ys) if pairs else IsotonicCalibrator([0.0], [0.5])
    )
    thresh_means = subset_means(conn, experiment_id, n_expected, thresh, exclude_judges)
    thresh_ps = [platt.predict(m) for m in thresh_means.values() if m is not None]
    grid = margin_grid(cfg.margin_step)
    return Exp2Fit(
        experiment_id=experiment_id,
        n_expected=n_expected,
        exclude_judges=sorted(exclude_judges),
        platt=platt,
        isotonic=isotonic.to_dict(),
        degenerate=not pairs or not thresh_ps,
        margins={
            cfg.target_key(t): (
                choose_margin(thresh_ps, t, grid)
                if thresh_ps
                else MarginChoice(margin=grid[0], achieved=0.0, reached=False)
            )
            for t in cfg.coverage_targets
        },
    )


async def fit_exp2_arm(
    conn: sqlite3.Connection,
    writer: SqliteStorageWriter,
    experiment_id: str,
    n_expected: int,
    calib: list[Sample],
    thresh: list[Sample],
    cfg: Exp2Config,
    *,
    allow_degenerate: bool = False,
) -> Exp2Fit:
    """Fit Platt on `calib`, choose margins on `thresh`, freeze under "fit".

    A degenerate fit (no valid calib or thresh sample) raises ValueError
    before anything is frozen unless `allow_degenerate` is set.
    """
    fit = _build_fit(conn, experiment_id, n_expected, calib, thresh, cfg, frozenset())
    if fit.degenerate and not allow_degenerate:
        raise ValueError(
            f"degenerate fit for {experiment_id!r}: no valid calib/thresh sample; "
            "check the answers first or pass allow_degenerate"
        )
    await writer.freeze_config(experiment_id, "fit", fit.model_dump())
    return fit


def fit_unfrozen(
    conn: sqlite3.Connection,
    experiment_id: str,
    n_expected: int,
    calib: list[Sample],
    thresh: list[Sample],
    cfg: Exp2Config,
    exclude_judges: frozenset[str],
) -> Exp2Fit:
    """Same fit as `fit_exp2_arm` but never freezes (derived analyses)."""
    return _build_fit(
        conn, experiment_id, n_expected, calib, thresh, cfg, exclude_judges
    )


def score_exp2(
    conn: sqlite3.Connection,
    fit: Exp2Fit,
    samples: list[Sample],
    *,
    calibrator: Literal["platt", "isotonic"] = "platt",
) -> list[Row]:
    """Apply the stored calibrator; invalid or degenerate rows keep `p = None`."""
    iso = IsotonicCalibrator.from_dict(fit.isotonic)
    means = subset_means(
        conn,
        fit.experiment_id,
        fit.n_expected,
        samples,
        frozenset(fit.exclude_judges),
    )
    rows = []
    for s in samples:
        mean = None if fit.degenerate else means[s.input_id]
        if mean is None:
            p = None
        elif calibrator == "platt":
            p = fit.platt.predict(mean)
        else:
            p = iso.predict(mean)
        rows.append(
            Row(
                input_id=s.input_id,
                regime=s.regime,
                label=s.label,
                t_index=s.t_index,
                p=p,
            )
        )
    return rows
