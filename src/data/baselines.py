"""LLM-free reference rules (spec §4.5).

Parameters are fitted on the `calib` split only. The regime-aware rule is
a reference point, not a guaranteed upper bound.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import BaseModel

from src.data.schema import Label, Regime, Sample

# 59 keeps `bars[-1 - lookback]` inside the default 60-bar window.
LOOKBACKS = (5, 10, 20, 59)


def accuracy(preds: list[Label], samples: list[Sample]) -> float:
    """Fraction of predictions equal to the sample label."""
    if not samples:
        raise ValueError("accuracy needs at least one sample")
    return sum(p == s.label for p, s in zip(preds, samples)) / len(samples)


def majority_label(samples: list[Sample]) -> Label:
    """Most frequent label; ties go to HIGH."""
    high = sum(s.label == "HIGH" for s in samples)
    return "HIGH" if high >= len(samples) - high else "LOW"


def momentum_signal(state: dict[str, Any], lookback: int, sign: int) -> Label:
    """Follow (sign=+1) or fade (sign=-1) the move over `lookback` bars."""
    bars = state["bars"]
    up = bars[-1] - bars[-1 - lookback] > 0
    if sign < 0:
        up = not up
    return "HIGH" if up else "LOW"


class MomentumRule(BaseModel):
    lookback: int
    sign: int

    def predict(self, state: dict[str, Any]) -> Label:
        return momentum_signal(state, self.lookback, self.sign)


def fit_momentum(samples: list[Sample]) -> MomentumRule:
    """Pick (lookback, sign) with the best accuracy; first wins on ties."""
    best: tuple[float, MomentumRule] | None = None
    for lookback in LOOKBACKS:
        for sign in (1, -1):
            rule = MomentumRule(lookback=lookback, sign=sign)
            acc = accuracy([rule.predict(s.state) for s in samples], samples)
            if best is None or acc > best[0]:
                best = (acc, rule)
    assert best is not None
    return best[1]


class RegimeAwareRule(BaseModel):
    default: MomentumRule
    rules: dict[Regime, MomentumRule]

    def predict(self, sample: Sample) -> Label:
        return self.rules.get(sample.regime, self.default).predict(sample.state)


def fit_regime_aware(samples: list[Sample]) -> RegimeAwareRule:
    """Fit one momentum rule per regime (uses the regime label by design)."""
    grouped: dict[Regime, list[Sample]] = defaultdict(list)
    for s in samples:
        grouped[s.regime].append(s)
    return RegimeAwareRule(
        default=fit_momentum(samples),
        rules={regime: fit_momentum(group) for regime, group in grouped.items()},
    )
