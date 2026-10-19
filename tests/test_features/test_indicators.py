"""Tests for the deterministic indicators and role states (spec section 4)."""

import math
import random

import pytest

from src.features.indicators import (
    ALL_KEYS,
    ROLE_INDICATORS,
    ROLES,
    all_state,
    compute_indicators,
    feature_vector,
    role_state,
)


def _walk(seed: int = 1, n: int = 60) -> list[float]:
    """Generated random-walk closes."""
    rng = random.Random(seed)
    price = 100.0
    out = []
    for _ in range(n):
        price *= math.exp(rng.gauss(0, 0.01))
        out.append(price)
    return out


def test_flat_window_is_degenerate_not_nan() -> None:
    ind = compute_indicators([1.1] * 60)
    assert ind["trend_slope_bp"] == 0
    assert ind["zscore20"] == 0
    assert ind["vol10_pct"] == 0 and ind["vol59_pct"] == 0
    assert ind["vol_ratio"] == 1
    assert ind["range_pos20"] == 0.5
    assert all(math.isfinite(v) for v in ind.values())


def test_linear_log_growth_slope() -> None:
    closes = [100 * math.exp(0.001 * i) for i in range(60)]
    ind = compute_indicators(closes)
    assert ind["trend_slope_bp"] == pytest.approx(10.0, abs=1e-3)
    assert ind["ret5_pct"] == pytest.approx(0.5, abs=1e-3)


def test_range_position_bounds() -> None:
    rising = [100 + i for i in range(60)]
    assert compute_indicators(rising)["range_pos20"] == 1.0
    assert compute_indicators(rising[::-1])["range_pos20"] == 0.0


def test_window_locality_and_length() -> None:
    closes = _walk(2)
    assert compute_indicators(closes) == compute_indicators(list(closes))
    with pytest.raises(ValueError):
        compute_indicators(closes[:59])
    with pytest.raises(ValueError):
        compute_indicators(closes + [closes[-1]])
    base = compute_indicators(closes)
    perturbed = list(closes)
    perturbed[0] *= 1.5
    other = compute_indicators(perturbed)
    for key in (
        "ret5_pct",
        "ret10_pct",
        "ret20_pct",
        "zscore20",
        "range_pos20",
        "close_vs_sma20_pct",
        "vol10_pct",
    ):
        assert other[key] == base[key]


def test_role_state_has_only_role_keys() -> None:
    closes = _walk(3)
    union: set[str] = set()
    total = 0
    for role in ROLES:
        assert set(role_state(closes, role)) == set(ROLE_INDICATORS[role])
        union |= set(ROLE_INDICATORS[role])
        total += len(ROLE_INDICATORS[role])
    assert total == len(union)
    assert set(all_state(closes)) == union == set(ALL_KEYS)


def test_values_rounded_to_four_decimals() -> None:
    for v in all_state(_walk(1)).values():
        assert round(v, 4) == v


def test_feature_vector_order_matches_keys() -> None:
    closes = _walk(4)
    assert feature_vector(closes) == [all_state(closes)[k] for k in ALL_KEYS]
