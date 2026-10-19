"""Experiment 2 pilot stop-rule checks (spec section 9)."""

import math
import sqlite3
from statistics import pstdev

from pydantic import BaseModel, Field

from src.data.schema import Sample
from src.experiments.exp2_config import Exp2Config
from src.features.indicators import compute_indicators
from src.storage.reader import load_probabilities


class PilotCheck(BaseModel):
    """Outcome of the pilot stop-rule checks; reasons are never hidden.

    `uninformative_roles` lists the judge ids (e.g. `role_trend`,
    `ap_judge#0`) whose probability std across pilot inputs is below
    `degenerate_std`.
    """

    stop: bool
    reasons: list[str] = Field(default_factory=list)
    invalid_rate: dict[str, float] = Field(default_factory=dict)
    judge_std: dict[str, float | None] = Field(default_factory=dict)
    uninformative_roles: list[str] = Field(default_factory=list)


def _nonfinite_indicator_inputs(pilot: list[Sample]) -> list[str]:
    """Input ids whose indicators cannot be computed or are non-finite."""
    bad: list[str] = []
    for s in pilot:
        try:
            ind = compute_indicators(s.state["bars"])
        except (ValueError, ArithmeticError, KeyError, TypeError):
            bad.append(s.input_id)
            continue
        if not all(math.isfinite(v) for v in ind.values()):
            bad.append(s.input_id)
    return bad


def pilot_check(
    conn: sqlite3.Connection,
    experiments: dict[str, int],
    pilot: list[Sample],
    cfg: Exp2Config,
) -> PilotCheck:
    """Evaluate the pilot stop rules for the given arms.

    `experiments` maps experiment id -> expected valid answers per sample.
    Stops on: an arm invalid rate above `cfg.pilot_invalid_max`, any
    non-finite indicator, or a Judge whose probability std across pilot
    inputs is below `cfg.degenerate_std`.
    """
    if not pilot:
        raise ValueError("pilot sample list is empty")
    ids = [s.input_id for s in pilot]
    reasons: list[str] = []
    invalid_rate: dict[str, float] = {}
    judge_std: dict[str, float | None] = {}
    uninformative: set[str] = set()

    for eid, n_expected in experiments.items():
        probs = load_probabilities(conn, eid)
        n_bad = sum(1 for i in ids if len(probs.get(i, {})) != n_expected)
        rate = n_bad / len(ids)
        invalid_rate[eid] = rate
        if rate > cfg.pilot_invalid_max:
            reasons.append(
                f"{eid}: invalid rate {rate:.3f} ({n_bad}/{len(ids)}) exceeds "
                f"{cfg.pilot_invalid_max}"
            )
        values: dict[str, list[float]] = {}
        for i in ids:
            for judge, p in probs.get(i, {}).items():
                values.setdefault(judge, []).append(p)
        for judge in sorted(values):
            vals = values[judge]
            std = pstdev(vals) if len(vals) >= 2 else None
            judge_std[f"{eid}:{judge}"] = std
            if std is not None and std < cfg.degenerate_std:
                uninformative.add(judge)
                reasons.append(
                    f"{eid}: judge {judge} is uninformative (std {std:.4f} < "
                    f"{cfg.degenerate_std})"
                )

    bad = _nonfinite_indicator_inputs(pilot)
    if bad:
        reasons.append(
            f"non-finite indicator on {len(bad)} pilot sample(s): {', '.join(bad)}"
        )
    return PilotCheck(
        stop=bool(reasons),
        reasons=reasons,
        invalid_rate=invalid_rate,
        judge_std=judge_std,
        uninformative_roles=sorted(uninformative),
    )
