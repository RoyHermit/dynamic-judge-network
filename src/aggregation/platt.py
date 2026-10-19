"""Platt scaling in pure Python (Experiment 2 spec §8).

Two-parameter logistic calibration on the logit of the mean probability,
solved with damped Newton steps and a hand-written 2x2 linear solve (no
numpy/scipy).
"""

from __future__ import annotations

import math

from pydantic import BaseModel

_CLIP = 1e-4
_MAX_ITER = 50
_TOL = 1e-9


def _sigmoid(z: float) -> float:
    """Numerically stable logistic function."""
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def logit_clip(p: float) -> float:
    """Clip p to [1e-4, 1 - 1e-4], then return log(p / (1 - p))."""
    q = min(max(p, _CLIP), 1.0 - _CLIP)
    return math.log(q / (1.0 - q))


def _nll(a: float, b: float, xs: list[float], ys: list[float], l2: float) -> float:
    """Penalised negative log-likelihood (softplus form, overflow-safe)."""
    total = l2 * b * b
    for x, y in zip(xs, ys):
        z = a + b * x
        total += max(z, 0.0) + math.log1p(math.exp(-abs(z))) - y * z
    return total


class PlattCalibrator(BaseModel):
    """p -> sigmoid(intercept + slope * logit_clip(p)), or a base-rate fallback.

    `fallback` is None for a fitted curve, otherwise one of "constant_input",
    "single_class", "separated", "fit_failed"; then `predict` returns the
    base rate. "nonpositive_slope" marks a fit whose slope was clamped to 0
    (intercept-only curve, so `predict` is also constant at the base rate).
    `base_rate` is the share of positive labels (0.5 if empty).
    """

    intercept: float
    slope: float
    fallback: str | None
    base_rate: float

    @classmethod
    def fit(cls, ps: list[float], ys: list[float], l2: float = 0.01) -> PlattCalibrator:
        """Fit by minimising NLL + l2 * slope**2 (intercept unpenalised).

        The slope is constrained to be >= 0: if the unconstrained optimum has a
        negative slope, the model is refitted intercept-only (intercept =
        logit of the clipped base rate) and recorded with fallback
        "nonpositive_slope", since its predictions are constant.
        Degenerate data (empty, constant inputs, single class, perfect
        separation) is detected BEFORE fitting and returns a fallback; so does
        non-convergence within 50 iterations or a non-finite parameter
        ("fit_failed"). Never raises on degenerate data.
        """
        n = len(ps)
        if n == 0:
            return cls(intercept=0.0, slope=0.0, fallback="single_class", base_rate=0.5)
        xs = [logit_clip(p) for p in ps]
        base = sum(ys) / n

        def fallback(name: str) -> PlattCalibrator:
            return cls(
                intercept=_logit_base(base), slope=0.0, fallback=name, base_rate=base
            )

        if max(xs) == min(xs):
            return fallback("constant_input")
        pos = [x for x, y in zip(xs, ys) if y >= 0.5]
        neg = [x for x, y in zip(xs, ys) if y < 0.5]
        if not pos or not neg:
            return fallback("single_class")
        if max(neg) < min(pos) or max(pos) < min(neg):
            return fallback("separated")

        result = _newton(xs, ys, l2)
        if result is None:
            return fallback("fit_failed")
        a, b = result
        if b < 0.0:
            return cls(
                intercept=_logit_base(base),
                slope=0.0,
                fallback="nonpositive_slope",
                base_rate=base,
            )
        return cls(intercept=a, slope=b, fallback=None, base_rate=base)

    def predict(self, p: float) -> float:
        """Calibrated probability in (0, 1); base rate (clipped) on fallback.

        "nonpositive_slope" keeps the intercept-only curve, whose value
        sigmoid(logit(clipped base rate)) is that same base rate.
        """
        if self.fallback not in (None, "nonpositive_slope"):
            return min(max(self.base_rate, _CLIP), 1.0 - _CLIP)
        return _sigmoid(self.intercept + self.slope * logit_clip(p))


def _logit_base(base: float) -> float:
    """Logit of the base rate clipped to [1e-4, 1 - 1e-4]."""
    return logit_clip(base)


def _newton(xs: list[float], ys: list[float], l2: float) -> tuple[float, float] | None:
    """Damped Newton on (intercept, slope); None if it fails to converge."""
    a, b = _logit_base(sum(ys) / len(ys)), 0.0
    cur = _nll(a, b, xs, ys, l2)
    for _ in range(_MAX_ITER):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in zip(xs, ys):
            s = _sigmoid(a + b * x)
            w = s * (1.0 - s)
            r = s - y
            ga += r
            gb += r * x
            haa += w
            hab += w * x
            hbb += w * x * x
        gb += 2.0 * l2 * b
        hbb += 2.0 * l2
        det = haa * hbb - hab * hab
        if not math.isfinite(det) or det <= 0.0:
            return None
        # Newton direction: solve H d = -g by the 2x2 closed form.
        da = -(hbb * ga - hab * gb) / det
        db = -(-hab * ga + haa * gb) / det
        # Backtracking line search keeps the objective monotone.
        step = 1.0
        for _ in range(30):
            na, nb = a + step * da, b + step * db
            new = _nll(na, nb, xs, ys, l2)
            if math.isfinite(new) and new <= cur + 1e-12:
                break
            step *= 0.5
        else:
            return None
        a, b, cur = na, nb, new
        if not (math.isfinite(a) and math.isfinite(b)):
            return None
        if max(abs(step * da), abs(step * db)) < _TOL:
            return a, b
    return None
