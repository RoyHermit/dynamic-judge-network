"""Experiment 2 preregistered success rule and cross-dataset verdict (pure logic)."""

from pydantic import BaseModel, Field

from src.metrics.paired import PairedDiff

# Tolerance for float rounding of count-ratio differences, not a tunable threshold.
_FLOAT_TOL = 1e-9


class DatasetVerdict(BaseModel):
    """Outcome of the success rule on one dataset."""

    passed: bool
    criteria: dict[str, bool]
    attributable: bool | None
    notes: list[str] = Field(default_factory=list)


def _ci_above_zero(p: PairedDiff) -> bool:
    """True when the CI exists and its lower bound is above zero."""
    return p.ci is not None and p.ci[0] > 0


def evaluate_dataset(
    d_vs_ap: PairedDiff,
    d_vs_majority: PairedDiff,
    d_vs_l: PairedDiff,
    d_vs_m: PairedDiff,
    d_vs_ap5: PairedDiff | None,
    min_gain: float,
) -> DatasetVerdict:
    """Apply the four-criteria success rule; a missing CI or diff counts as not met."""
    notes: list[str] = []

    def unusable(p: PairedDiff, name: str) -> bool:
        if p.ci is None or p.diff is None:
            notes.append(f"{name}: CI or diff unavailable; criterion not met")
            return True
        return False

    criteria = {
        "D>A' (+3pt)": (
            not unusable(d_vs_ap, "D vs A'")
            and _ci_above_zero(d_vs_ap)
            and d_vs_ap.diff is not None  # narrowing for type checkers only
            and d_vs_ap.diff >= min_gain - _FLOAT_TOL
        ),
        "D>Majority": not unusable(d_vs_majority, "D vs Majority")
        and _ci_above_zero(d_vs_majority),
        "D>L": not unusable(d_vs_l, "D vs L") and _ci_above_zero(d_vs_l),
        "D>M": not unusable(d_vs_m, "D vs M") and _ci_above_zero(d_vs_m),
    }
    attributable = None if d_vs_ap5 is None else _ci_above_zero(d_vs_ap5)
    return DatasetVerdict(
        passed=all(criteria.values()),
        criteria=criteria,
        attributable=attributable,
        notes=notes,
    )


def _attribution_tail(attributable: bool) -> str:
    """The §5 attribution sentence shared by every passing verdict."""
    if attributable:
        return "the gain is attributable to role decomposition (D also beats A'x5)."
    return (
        "the gain is not separable from replication/compute "
        "(D does not beat A'x5, or A'x5 was not evaluated)."
    )


def combine(ecb: DatasetVerdict, synthetic: DatasetVerdict) -> tuple[str, str]:
    """Map the two dataset verdicts to (label, wording) per the verdict table.

    Every passing label carries the §5 attribution tail: attributable only
    when D also beats A'x5 on each dataset that passed.
    """
    if ecb.passed and synthetic.passed:
        tail = _attribution_tail(bool(ecb.attributable and synthetic.attributable))
        return (
            "Strong success",
            "Role decomposition helps on both real and synthetic data; " + tail,
        )
    if ecb.passed:
        return (
            "Exploratory success",
            (
                "Positive on real data, but prior knowledge from Experiment 1 "
                "informed the design; fresh data is needed to confirm; "
                + _attribution_tail(bool(ecb.attributable))
            ),
        )
    if synthetic.passed:
        return (
            "Mechanism works, no real-data evidence",
            (
                "The mechanism works on synthetic data but real data shows no "
                "evidence of a benefit."
            ),
        )
    return (
        "Failure",
        "Role decomposition did not meet the success rule on either dataset.",
    )
