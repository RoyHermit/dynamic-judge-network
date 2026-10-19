"""Platt calibrator (Experiment 2 spec §8)."""

import math
import random

import pytest

from src.aggregation.platt import PlattCalibrator, logit_clip


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def test_recovers_known_curve():
    rng = random.Random(0)
    ps = [rng.uniform(0.05, 0.95) for _ in range(2000)]
    ys = [
        1.0 if rng.random() < _sigmoid(0.5 + 1.5 * logit_clip(p)) else 0.0 for p in ps
    ]
    cal = PlattCalibrator.fit(ps, ys)
    assert cal.fallback is None
    assert cal.slope == pytest.approx(1.5, abs=0.2)
    assert cal.intercept == pytest.approx(0.5, abs=0.2)


def test_slope_never_negative():
    rng = random.Random(1)
    ps = [rng.uniform(0.05, 0.95) for _ in range(500)]
    ys = [1.0 if rng.random() < 1.0 - p else 0.0 for p in ps]
    cal = PlattCalibrator.fit(ps, ys)
    assert cal.slope == 0.0
    assert cal.fallback is None
    base = min(max(cal.base_rate, 1e-4), 1 - 1e-4)
    for x in (0.1, 0.5, 0.9):
        assert cal.predict(x) == pytest.approx(base, abs=1e-9)


@pytest.mark.parametrize(
    ("ps", "ys", "expected"),
    [
        ([0.5, 0.5, 0.5, 0.5], [1.0, 0.0, 1.0, 0.0], "constant_input"),
        ([0.2, 0.4, 0.6, 0.8], [1.0, 1.0, 1.0, 1.0], "single_class"),
        ([0.2, 0.4, 0.6, 0.8], [0.0, 0.0, 1.0, 1.0], "separated"),
        ([0.2, 0.4, 0.6, 0.8], [1.0, 1.0, 0.0, 0.0], "separated"),
        ([], [], "single_class"),
    ],
)
def test_fallbacks_recorded(ps, ys, expected):
    cal = PlattCalibrator.fit(ps, ys)
    assert cal.fallback == expected
    for x in (0.0, 0.3, 1.0):
        assert cal.predict(x) == pytest.approx(min(max(cal.base_rate, 1e-4), 1 - 1e-4))
    if not ps:
        assert cal.base_rate == 0.5


def test_extreme_probabilities_clipped():
    ps = [0.0, 1.0, 0.3, 0.7, 0.5, 0.1, 0.9, 0.6]
    ys = [0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]
    cal = PlattCalibrator.fit(ps, ys)
    for x in (0.0, 1.0):
        assert 0.0 < cal.predict(x) < 1.0


def test_round_trip_dict():
    rng = random.Random(2)
    ps = [rng.uniform(0.1, 0.9) for _ in range(200)]
    ys = [1.0 if rng.random() < p else 0.0 for p in ps]
    cal = PlattCalibrator.fit(ps, ys)
    assert PlattCalibrator.model_validate(cal.model_dump()) == cal
