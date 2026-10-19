"""Moving-block paired bootstrap (spec §7)."""

import random

from src.metrics.bootstrap import moving_block_resample, paired_block_ci


def test_resample_has_n_indices_in_range_and_is_seeded():
    a = moving_block_resample(10, 4, random.Random(0))
    b = moving_block_resample(10, 4, random.Random(0))
    assert a == b and len(a) == 10 and all(0 <= i < 10 for i in a)
    assert moving_block_resample(0, 4, random.Random(0)) == []


def test_blocks_are_contiguous_runs():
    idx = moving_block_resample(12, 4, random.Random(1))
    for start in (0, 4, 8):
        block = idx[start : start + 4]
        assert block == list(range(block[0], block[0] + 4))


def test_ci_brackets_a_constant_statistic_and_returns_none_when_undefined():
    ci = paired_block_ci(20, 5, 50, 0, lambda idx: 0.25)
    assert ci == (0.25, 0.25)
    assert paired_block_ci(20, 5, 50, 0, lambda idx: None) is None
