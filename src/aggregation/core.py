"""Mean, isotonic calibration, decision rule and margin selection (spec §6).

Isotonic regression is the standard pool-adjacent-violators algorithm,
implemented here directly (no new dependency).
"""

from __future__ import annotations

from bisect import bisect_right
from typing import Literal

from pydantic import BaseModel

Decision = Literal["HIGH", "LOW", "SKIP"]
_EPS = 1e-12


def mean_probability(values: list[float], n_expected: int) -> float | None:
    """Mean of exactly `n_expected` valid values, else None (invalid sample)."""
    if len(values) != n_expected:
        return None
    return sum(values) / n_expected


class IsotonicCalibrator:
    """Non-decreasing step function fitted by pooling adjacent violators."""

    def __init__(self, xs: list[float], values: list[float]) -> None:
        self._xs = xs  # lower bound of each pooled block, ascending
        self._values = values

    @classmethod
    def fit(cls, ps: list[float], ys: list[float]) -> IsotonicCalibrator:
        if not ps:
            raise ValueError("cannot fit a calibrator on no data")
        grouped: dict[float, list[float]] = {}
        for p, y in zip(ps, ys):
            cell = grouped.setdefault(p, [0.0, 0.0])
            cell[0] += 1.0
            cell[1] += y
        blocks: list[list[float]] = []  # [x_lo, weight, sum_y]
        for x in sorted(grouped):
            weight, total = grouped[x]
            blocks.append([x, weight, total])
            while (
                len(blocks) >= 2
                and blocks[-2][2] / blocks[-2][1] > blocks[-1][2] / blocks[-1][1]
            ):
                _, weight2, total2 = blocks.pop()
                blocks[-1][1] += weight2
                blocks[-1][2] += total2
        return cls([b[0] for b in blocks], [b[2] / b[1] for b in blocks])

    def predict(self, p: float) -> float:
        # Clamp instead of extrapolating outside the fitted range.
        index = max(bisect_right(self._xs, p) - 1, 0)
        return self._values[index]

    def to_dict(self) -> dict[str, list[float]]:
        return {"xs": list(self._xs), "values": list(self._values)}

    @classmethod
    def from_dict(cls, data: dict[str, list[float]]) -> IsotonicCalibrator:
        return cls(list(data["xs"]), list(data["values"]))


def decide(p: float, m: float) -> Decision:
    """HIGH/LOW/SKIP for calibrated probability `p` and margin `m >= 0`.

    Inclusive at the margin boundary for m > 0; exactly p = 0.5 is always
    SKIP so the two branches are mutually exclusive at m = 0.
    """
    # Compare distances from 0.5 with a tiny tolerance: 0.5 - 0.4 is not
    # exactly 0.1 in floating point, and the boundary is inclusive.
    if p > 0.5 and p - 0.5 >= m - _EPS:
        return "HIGH"
    if p < 0.5 and 0.5 - p >= m - _EPS:
        return "LOW"
    return "SKIP"


def margin_grid(step: float) -> list[float]:
    """Ascending margins 0, step, 2*step, ... up to 0.5."""
    return [round(i * step, 10) for i in range(round(0.5 / step) + 1)]


class MarginChoice(BaseModel):
    margin: float
    achieved: float  # coverage over the valid thresh samples
    reached: bool  # False when the target is unattainable (spec §6.4)


def _coverage(ps: list[float], m: float) -> float:
    return sum(decide(p, m) != "SKIP" for p in ps) / len(ps)


def choose_margin(ps: list[float], target: float, grid: list[float]) -> MarginChoice:
    """Largest grid margin whose coverage is at least `target`.

    Coverage is non-increasing in the margin, so scan from the top. When
    even the smallest margin falls short (p = 0.5 plateaus), return it
    with `reached=False`.
    """
    if not ps:
        raise ValueError("no thresh samples to choose a margin from")
    for m in sorted(grid, reverse=True):
        coverage = _coverage(ps, m)
        if coverage + 1e-12 >= target:
            return MarginChoice(margin=m, achieved=coverage, reached=True)
    smallest = min(grid)
    return MarginChoice(
        margin=smallest, achieved=_coverage(ps, smallest), reached=False
    )
