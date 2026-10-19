"""Tests for deterministic competitors (Experiment 2 spec §3, §8)."""

from src.data.competitors import competitor_rows, fit_competitors
from src.data.schema import Sample
from src.data.synthetic import SyntheticConfig, SyntheticSource


def _splits() -> tuple[list[Sample], list[Sample], list[Sample]]:
    src = SyntheticSource(
        SyntheticConfig(
            seed=7,
            split_sizes={
                "pilot": 10,
                "calib": 60,
                "thresh": 40,
                "test": 30,
                "test_shift": 20,
            },
        )
    )
    return src.samples("calib"), src.samples("thresh"), src.samples("test")


def test_competitors_use_calib_only():
    calib, thresh, _ = _splits()
    base = fit_competitors(calib, thresh)
    flipped = [
        s.model_copy(update={"label": "LOW" if s.label == "HIGH" else "HIGH"})
        for s in thresh
    ]
    other = fit_competitors(calib, flipped)
    assert other.majority == base.majority
    assert other.const_p == base.const_p
    assert other.momentum == base.momentum


def test_competitor_rows_valid_and_aligned():
    calib, thresh, ev = _splits()
    c = fit_competitors(calib, thresh)
    rows = competitor_rows(c, ev)
    assert set(rows) == {"L", "M", "Majority", "Const"}
    for rs in rows.values():
        assert [r.input_id for r in rs] == [s.input_id for s in ev]
        assert all(r.p is not None for r in rs)
    assert all(r.p in (0.0, 1.0) for r in rows["M"] + rows["Majority"])


def test_empty_thresh_uses_middle_l2():
    calib, _, _ = _splits()
    c = fit_competitors(calib, [])
    assert c.chosen_l2 == 1.0
