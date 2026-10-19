"""Aggregation rules (spec §6)."""

import pytest

from src.aggregation.core import (
    IsotonicCalibrator,
    choose_margin,
    decide,
    margin_grid,
    mean_probability,
)


def test_mean_requires_exactly_n_valid_values():
    assert mean_probability([0.2, 0.4], 2) == pytest.approx(0.3)
    assert mean_probability([0.2], 2) is None  # survivors are never averaged
    assert mean_probability([], 5) is None


def test_decide_boundaries_and_exact_half_is_skip():
    assert decide(0.75, 0.25) == "HIGH"  # inclusive for m > 0
    assert decide(0.25, 0.25) == "LOW"
    assert decide(0.5, 0.0) == "SKIP"  # branches must not both fire at m = 0
    assert decide(0.5000001, 0.0) == "HIGH"
    assert decide(0.4999999, 0.0) == "LOW"
    assert decide(0.6, 0.25) == "SKIP"


def test_isotonic_pools_violations_and_clamps():
    cal = IsotonicCalibrator.fit([0.1, 0.2, 0.3, 0.4], [0, 1, 0, 1])
    assert cal.predict(0.1) == 0.0
    assert cal.predict(0.3) == 0.5  # pooled with 0.2
    assert cal.predict(0.4) == 1.0
    assert cal.predict(0.05) == 0.0  # below range: clamped
    assert cal.predict(0.9) == 1.0  # above range: clamped


def test_isotonic_pools_equal_inputs_and_handles_constant_data():
    assert IsotonicCalibrator.fit([0.5, 0.5], [0, 1]).predict(0.5) == 0.5
    constant = IsotonicCalibrator.fit([0.7, 0.7, 0.7], [1, 1, 0])
    assert constant.predict(0.1) == constant.predict(0.9) == pytest.approx(2 / 3)


def test_isotonic_roundtrip_and_empty_fit():
    cal = IsotonicCalibrator.fit([0.1, 0.5, 0.9], [0, 1, 1])
    again = IsotonicCalibrator.from_dict(cal.to_dict())
    probes = (0.0, 0.5, 1.0)
    assert [again.predict(p) for p in probes] == [cal.predict(p) for p in probes]
    with pytest.raises(ValueError):
        IsotonicCalibrator.fit([], [])


def test_choose_margin_takes_largest_margin_meeting_target():
    ps = [0.95, 0.75, 0.5, 0.25, 0.05]
    grid = [0.0, 0.1, 0.2, 0.3, 0.4]
    assert choose_margin(ps, 0.8, grid).margin == 0.2
    assert choose_margin(ps, 0.4, grid).margin == 0.4
    unreachable = choose_margin(ps, 1.0, grid)  # p = 0.5 is always SKIP
    assert (unreachable.margin, unreachable.achieved, unreachable.reached) == (
        0.0,
        0.8,
        False,
    )


def test_choose_margin_rejects_empty_input_and_margin_grid_spans_half():
    with pytest.raises(ValueError):
        choose_margin([], 0.8, [0.0])
    grid = margin_grid(0.1)
    assert grid[0] == 0.0 and grid[-1] == 0.5 and len(grid) == 6


def test_decide_boundary_survives_float_subtraction():
    # 0.5 - 0.4 is 0.09999999999999998 in floating point; the boundary is inclusive.
    assert decide(0.1, 0.4) == "LOW"
    assert decide(0.9, 0.4) == "HIGH"
    assert decide(0.15, 0.4) == "SKIP"
