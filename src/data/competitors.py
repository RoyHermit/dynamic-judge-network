"""Deterministic competitors L, M, Majority, Const (Experiment 2 spec §3, §8).

Everything is fitted on `calib` only; `thresh` is used solely to pick the
L2 strength of the logistic model.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.aggregation.logistic import LogisticModel, fit_logistic
from src.data.baselines import MomentumRule, fit_momentum, majority_label
from src.data.schema import Label, Sample
from src.features.indicators import feature_vector
from src.metrics.core import Row, log_loss

LOG_LOSS_DELTA = 1e-6
DEFAULT_L2_GRID: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0, 100.0)


class Competitors(BaseModel):
    logistic: LogisticModel
    chosen_l2: float
    momentum: MomentumRule
    majority: Label
    const_p: float


def _features(samples: list[Sample]) -> list[list[float]]:
    return [feature_vector(s.state["bars"]) for s in samples]


def _targets(samples: list[Sample]) -> list[float]:
    return [1.0 if s.label == "HIGH" else 0.0 for s in samples]


def _row(s: Sample, p: float) -> Row:
    return Row(
        input_id=s.input_id, regime=s.regime, label=s.label, t_index=s.t_index, p=p
    )


def fit_competitors(
    calib: list[Sample],
    thresh: list[Sample],
    l2_grid: tuple[float, ...] = DEFAULT_L2_GRID,
) -> Competitors:
    """Fit all competitors on `calib`; choose l2 on `thresh` by log loss.

    Ties go to the larger l2. With an empty `thresh` the middle grid value
    (sorted order) is used, since there is nothing to select on.
    """
    xs, ys = _features(calib), _targets(calib)
    grid = sorted(l2_grid)
    models = {l2: fit_logistic(xs, ys, l2) for l2 in grid}
    if thresh:
        tx = _features(thresh)
        losses: dict[float, float] = {}
        for l2, model in models.items():
            rows = [_row(s, model.predict(x)) for s, x in zip(thresh, tx)]
            loss = log_loss(rows, LOG_LOSS_DELTA)
            assert loss is not None
            losses[l2] = loss
        # Iterating ascending with <= makes the larger l2 win ties.
        chosen = grid[0]
        for l2 in grid:
            if losses[l2] <= losses[chosen]:
                chosen = l2
    else:
        chosen = grid[len(grid) // 2]
    return Competitors(
        logistic=models[chosen],
        chosen_l2=chosen,
        momentum=fit_momentum(calib),
        majority=majority_label(calib),
        const_p=sum(ys) / len(ys),
    )


def competitor_rows(c: Competitors, samples: list[Sample]) -> dict[str, list[Row]]:
    """Rows for arms L, M, Majority and Const; `p` is never None."""
    out: dict[str, list[Row]] = {"L": [], "M": [], "Majority": [], "Const": []}
    for s in samples:
        out["L"].append(_row(s, c.logistic.predict(feature_vector(s.state["bars"]))))
        out["M"].append(_row(s, 1.0 if c.momentum.predict(s.state) == "HIGH" else 0.0))
        out["Majority"].append(_row(s, 1.0 if c.majority == "HIGH" else 0.0))
        out["Const"].append(_row(s, c.const_p))
    return out
