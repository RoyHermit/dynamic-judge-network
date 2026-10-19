"""Tests for the LLM-free reference rules (spec §4.5)."""

from src.data.baselines import (
    accuracy,
    fit_momentum,
    fit_regime_aware,
    majority_label,
    momentum_signal,
)
from src.data.schema import Sample
from src.data.synthetic import SyntheticConfig, generate


def _sample(bars, label, regime="trend", i=0) -> Sample:
    return Sample(
        input_id=f"s{i}",
        state={"bars": bars},
        label=label,
        split="calib",
        regime=regime,
        t_index=i,
    )


def test_majority_label_prefers_high_on_tie():
    flat = [1.0] * 60
    assert majority_label([_sample(flat, "LOW"), _sample(flat, "HIGH")]) == "HIGH"
    assert majority_label([_sample(flat, "LOW")]) == "LOW"


def test_momentum_signal_direction_and_sign():
    up = [float(k) for k in range(60)]
    assert momentum_signal({"bars": up}, 5, 1) == "HIGH"
    assert momentum_signal({"bars": up}, 5, -1) == "LOW"


def test_fit_momentum_learns_direction():
    up = [float(k) for k in range(60)]
    down = [float(60 - k) for k in range(60)]
    follow = [_sample(up, "HIGH", i=1), _sample(down, "LOW", i=2)]
    reverse = [_sample(up, "LOW", i=1), _sample(down, "HIGH", i=2)]
    assert fit_momentum(follow).sign == 1
    assert fit_momentum(reverse).sign == -1
    rule = fit_momentum(follow)
    assert accuracy([rule.predict(s.state) for s in follow], follow) == 1.0


def test_momentum_is_near_chance_on_random_walk():
    # Labels are independent increments, so a fixed rule is a martingale
    # difference sum: std ~ 0.5/sqrt(n). Doubles as a leak detector.
    cfg = SyntheticConfig(
        seed=3,
        split_sizes={
            "pilot": 5,
            "calib": 3000,
            "thresh": 5,
            "test": 5,
            "test_shift": 5,
        },
    )
    calib = [s for s in generate(cfg).samples if s.split == "calib"]
    walk = [s for s in calib if s.regime == "random_walk"]
    assert len(walk) > 300
    acc = accuracy([momentum_signal(s.state, 20, 1) for s in walk], walk)
    assert 0.42 <= acc <= 0.58


def test_regime_aware_fits_at_least_as_well_as_global_in_sample():
    cfg = SyntheticConfig(
        seed=4,
        split_sizes={
            "pilot": 5,
            "calib": 1500,
            "thresh": 5,
            "test": 5,
            "test_shift": 5,
        },
    )
    calib = [s for s in generate(cfg).samples if s.split == "calib"]
    global_rule = fit_momentum(calib)
    regime_rule = fit_regime_aware(calib)
    acc_global = accuracy([global_rule.predict(s.state) for s in calib], calib)
    acc_regime = accuracy([regime_rule.predict(s) for s in calib], calib)
    assert acc_regime >= acc_global
