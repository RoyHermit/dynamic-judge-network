"""Tests for the Experiment 2 success rule and cross-dataset verdict."""

from src.experiments.verdict import DatasetVerdict, combine, evaluate_dataset
from src.metrics.paired import PairedDiff

GAIN = 0.03


def pd(diff: float | None, lo: float | None = 0.01) -> PairedDiff:
    """Build a PairedDiff with a CI starting at lo (None -> no CI)."""
    ci = None if lo is None else (lo, (lo + 0.05))
    return PairedDiff(n=100, acc_x=0.8, acc_y=0.7, diff=diff, ci=ci)


def good() -> PairedDiff:
    return pd(0.05, 0.01)


def verdict(**over: PairedDiff | None) -> DatasetVerdict:
    args: dict[str, PairedDiff | None] = {
        "d_vs_ap": good(),
        "d_vs_majority": good(),
        "d_vs_l": good(),
        "d_vs_m": good(),
        "d_vs_ap5": good(),
    }
    args.update(over)
    return evaluate_dataset(min_gain=GAIN, **args)  # type: ignore[arg-type]


def test_gain_gate_applies_only_to_d_vs_ap() -> None:
    v = verdict(d_vs_ap=pd(0.025), d_vs_majority=pd(0.01))
    assert v.criteria["D>A' (+3pt)"] is False
    assert v.criteria["D>Majority"] is True
    assert v.passed is False


def test_all_pass() -> None:
    v = verdict()
    assert v.passed is True
    assert set(v.criteria) == {"D>A' (+3pt)", "D>Majority", "D>L", "D>M"}
    assert v.attributable is True


def test_all_four_must_hold() -> None:
    bad = pd(0.05, -0.01)
    for key in ["d_vs_ap", "d_vs_majority", "d_vs_l", "d_vs_m"]:
        assert verdict(**{key: bad}).passed is False


def test_none_ci_is_not_met_not_error() -> None:
    v = verdict(d_vs_l=pd(None, None))
    assert v.criteria["D>L"] is False
    assert v.passed is False
    assert any("D vs L" in n for n in v.notes)
    v2 = verdict(d_vs_ap=pd(None, None))
    assert v2.criteria["D>A' (+3pt)"] is False
    assert any("A'" in n for n in v2.notes)


def test_verdict_table() -> None:
    p, f = verdict(), verdict(d_vs_m=pd(0.05, -0.01))
    assert combine(p, p)[0] == "Strong success"
    assert combine(p, f)[0] == "Exploratory success"
    assert combine(f, p)[0] == "Mechanism works, no real-data evidence"
    assert combine(f, f)[0] == "Failure"


def test_attribution_wording() -> None:
    p = verdict()
    label, text = combine(p, p)
    assert label == "Strong success"
    assert "attributable to role decomposition" in text
    assert "not separable" not in text
    no_attr = verdict(d_vs_ap5=pd(0.01, -0.01))
    assert no_attr.attributable is False
    _, text2 = combine(p, no_attr)
    assert "not separable from replication/compute" in text2
    assert "attributable to role decomposition" not in text2


def test_missing_ap5_leaves_attribution_none() -> None:
    v = verdict(d_vs_ap5=None)
    assert v.attributable is None
    _, text = combine(v, v)
    assert "not separable" in text
