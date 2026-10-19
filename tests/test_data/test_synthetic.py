"""Tests for the seeded synthetic generator (spec §4)."""

import itertools
import math

import pytest
from pydantic import ValidationError

from src.data.schema import SPLITS
from src.data.synthetic import SyntheticConfig, SyntheticSource, generate

SIZES = {"pilot": 10, "calib": 40, "thresh": 40, "test": 40, "test_shift": 40}


def _cfg(**kwargs) -> SyntheticConfig:
    return SyntheticConfig(seed=1, split_sizes=SIZES, **kwargs)


def test_same_seed_is_deterministic_and_other_seed_differs():
    assert generate(_cfg()) == generate(_cfg())
    other = generate(SyntheticConfig(seed=2, split_sizes=SIZES))
    assert generate(_cfg()).bars != other.bars


def test_state_contains_only_past_bars_and_label_uses_future():
    cfg = _cfg()
    data = generate(cfg)
    assert data.samples
    for s in data.samples:
        t = s.t_index
        assert s.state["bars"] == [
            round(b, 4) for b in data.bars[t - cfg.window + 1 : t + 1]
        ]
        assert len(s.state["bars"]) == cfg.window
        assert set(s.state) == {"bars"}  # no regime or label leakage
        ret = math.log(data.bars[t + cfg.horizon] / data.bars[t])
        assert s.label == ("HIGH" if ret > 0 else "LOW")


def test_embargo_separates_consecutive_splits():
    cfg = _cfg()
    data = generate(cfg)
    by_split = {sp: [s.t_index for s in data.samples if s.split == sp] for sp in SPLITS}
    for a, b in itertools.pairwise(SPLITS):
        gap = (min(by_split[b]) - cfg.window + 1) - (max(by_split[a]) + cfg.horizon)
        assert gap >= cfg.embargo_bars


def test_ties_are_excluded_and_counted():
    cfg = _cfg(epsilon=10.0)  # every |return| is below epsilon
    data = generate(cfg)
    assert data.samples == []
    assert data.excluded == SIZES


def test_every_candidate_is_labelled_or_excluded():
    data = generate(_cfg())
    assert len(data.samples) + sum(data.excluded.values()) == sum(SIZES.values())


def test_stride_must_cover_horizon_and_embargo_must_cover_window_plus_horizon():
    with pytest.raises(ValidationError):
        SyntheticConfig(stride=1, horizon=5)
    with pytest.raises(ValidationError):
        SyntheticConfig(window=60, horizon=5, embargo=10)


def test_source_returns_split_samples_only():
    source = SyntheticSource(_cfg())
    assert {s.split for s in source.samples("calib")} == {"calib"}
