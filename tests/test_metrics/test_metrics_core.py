"""Hand-computable metric tables (spec §7)."""

import math

import pytest

from src.metrics.core import (
    Row,
    accuracy_at_coverage,
    acted_accuracy_coverage,
    brier,
    log_loss,
    percentile,
    reliability,
    risk_coverage,
)


def _rows() -> list[Row]:
    spec = [(0.9, "HIGH"), (0.8, "LOW"), (0.2, "LOW"), (0.5, "HIGH"), (None, "HIGH")]
    return [
        Row(input_id=f"i{k}", regime="trend", label=label, t_index=k, p=p)
        for k, (p, label) in enumerate(spec)
    ]


def test_acted_accuracy_and_both_coverages():
    result = acted_accuracy_coverage(_rows(), 0.25)
    assert result.n_acted == 3 and result.n_valid == 4
    assert result.accuracy == pytest.approx(2 / 3)
    assert result.coverage_valid == pytest.approx(3 / 4)
    assert result.coverage_all == pytest.approx(3 / 5)  # invalid counts as not acted


def test_empty_acted_and_empty_valid_sets_give_none():
    all_skip = [r for r in _rows() if r.p == 0.5]
    assert acted_accuracy_coverage(all_skip, 0.0).accuracy is None
    assert acted_accuracy_coverage([], 0.1).coverage_valid is None
    invalid_only = [r for r in _rows() if r.p is None]
    assert acted_accuracy_coverage(invalid_only, 0.1).coverage_valid is None
    assert brier(invalid_only) is None and log_loss(invalid_only, 1e-6) is None


def test_brier_and_log_loss_over_valid_rows():
    assert brier(_rows()) == pytest.approx((0.01 + 0.64 + 0.04 + 0.25) / 4)
    expected = -(math.log(0.9) + math.log(0.2) + math.log(0.8) + math.log(0.5)) / 4
    assert log_loss(_rows(), 1e-6) == pytest.approx(expected)


def test_log_loss_clips_only_for_the_computation():
    rows = [Row(input_id="i", regime="r", label="LOW", t_index=0, p=1.0)]
    assert log_loss(rows, 1e-6) == pytest.approx(-math.log(1e-6))
    assert rows[0].p == 1.0


def test_risk_coverage_and_interpolation():
    curve = risk_coverage(_rows(), [0.0, 0.25, 0.39])
    assert [round(c.coverage, 4) for c in curve] == [0.75, 0.75, 0.25]
    assert curve[-1].accuracy == 1.0
    assert accuracy_at_coverage(curve, 0.5) == pytest.approx(1.0 - 0.5 * (1 / 3))
    assert accuracy_at_coverage(curve, 0.9) is None  # above the reachable range
    assert accuracy_at_coverage(curve, 0.1) is None  # below the reachable range


def test_reliability_bins_and_percentile():
    bins = reliability(_rows(), bins=2)
    assert [b["n"] for b in bins] == [1, 3]  # p<0.5 -> bin 0; 0.5,0.8,0.9 -> bin 1
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.95) == 4.0
