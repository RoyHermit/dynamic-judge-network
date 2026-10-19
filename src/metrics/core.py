"""Row-level metrics for one arm (spec §7). Pure functions, no I/O."""

from __future__ import annotations

import itertools
import math

from pydantic import BaseModel

from src.aggregation.core import decide
from src.data.schema import Label


class Row(BaseModel):
    """One sample's result for one arm; `p` is None for an invalid sample."""

    input_id: str
    regime: str
    label: Label
    t_index: int
    p: float | None  # calibrated P(HIGH)


class AccCov(BaseModel):
    accuracy: float | None  # among acted samples
    coverage_valid: float | None  # acted / valid
    coverage_all: float  # acted / all labelled (invalid counts as not acted)
    n_valid: int
    n_acted: int


def acted_accuracy_coverage(rows: list[Row], margin: float) -> AccCov:
    valid = [r for r in rows if r.p is not None]
    decided = [(r, decide(r.p, margin)) for r in valid]
    acted = [(r, d) for r, d in decided if d != "SKIP"]
    correct = sum(d == r.label for r, d in acted)
    return AccCov(
        accuracy=correct / len(acted) if acted else None,
        coverage_valid=len(acted) / len(valid) if valid else None,
        coverage_all=len(acted) / len(rows) if rows else 0.0,
        n_valid=len(valid),
        n_acted=len(acted),
    )


def brier(rows: list[Row]) -> float | None:
    valid = [r for r in rows if r.p is not None]
    if not valid:
        return None
    return sum((r.p - (r.label == "HIGH")) ** 2 for r in valid) / len(valid)


def log_loss(rows: list[Row], delta: float) -> float | None:
    """Mean negative log-likelihood; probabilities are clipped to
    [delta, 1 - delta] for this computation only."""
    valid = [r for r in rows if r.p is not None]
    if not valid:
        return None
    total = 0.0
    for r in valid:
        p = min(max(r.p, delta), 1.0 - delta)
        total -= math.log(p if r.label == "HIGH" else 1.0 - p)
    return total / len(valid)


class CurvePoint(BaseModel):
    margin: float
    coverage: float  # acted / valid
    accuracy: float | None


def risk_coverage(rows: list[Row], grid: list[float]) -> list[CurvePoint]:
    points: list[CurvePoint] = []
    for m in grid:
        result = acted_accuracy_coverage(rows, m)
        if result.coverage_valid is None:
            continue
        points.append(
            CurvePoint(
                margin=m, coverage=result.coverage_valid, accuracy=result.accuracy
            )
        )
    return points


def accuracy_at_coverage(curve: list[CurvePoint], level: float) -> float | None:
    """Linear interpolation of accuracy at `level`; None outside the
    range the arm can reach (spec §6.6)."""
    points = sorted(
        (c for c in curve if c.accuracy is not None), key=lambda c: c.coverage
    )
    for lo, hi in itertools.pairwise(points):
        if lo.coverage <= level <= hi.coverage and hi.coverage > lo.coverage:
            t = (level - lo.coverage) / (hi.coverage - lo.coverage)
            return lo.accuracy + t * (hi.accuracy - lo.accuracy)
    for p in points:
        if abs(p.coverage - level) < 1e-12:
            return p.accuracy
    return None


def reliability(rows: list[Row], bins: int = 10) -> list[dict]:
    """Per-bin count, mean predicted P(HIGH) and observed HIGH frequency."""
    out = [{"bin": b, "n": 0, "sum_p": 0.0, "sum_high": 0.0} for b in range(bins)]
    for r in rows:
        if r.p is None:
            continue
        cell = out[min(int(r.p * bins), bins - 1)]
        cell["n"] += 1
        cell["sum_p"] += r.p
        cell["sum_high"] += r.label == "HIGH"
    return [
        {
            "bin": c["bin"],
            "n": c["n"],
            "mean_p": c["sum_p"] / c["n"] if c["n"] else None,
            "frac_high": c["sum_high"] / c["n"] if c["n"] else None,
        }
        for c in out
    ]


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile, q in (0, 1]."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]
