"""Experiment 2 arm specs: A' (all indicators) and D (role-decomposed)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from src.data.schema import Sample
from src.experiments.runner import ArmLike, ArmSpec
from src.features.indicators import ROLES, all_state, role_state
from src.judges.definitions.indicator_judge import (
    AllIndicatorsJudge,
    RoleJudge,
    judge_from_id,
)
from src.judges.interface import Judge, State


class Exp2ArmSpec(BaseModel):
    """A' (single request), A'5 (five replicas) or D (five role requests)."""

    study_id: str
    arm: Literal["Ap", "Ap5", "D"]
    n_replicas: int = 5
    horizon: int = 5

    @property
    def experiment_id(self) -> str:
        return f"{self.study_id}-{self.arm}"

    def units(self) -> list[tuple[int, list[Judge]]]:
        """(stage_index, judges) units; every unit is a separate request."""
        if self.arm == "Ap":
            return [(0, [AllIndicatorsJudge(self.horizon)])]
        if self.arm == "Ap5":
            return [
                (k, [AllIndicatorsJudge(self.horizon, k)])
                for k in range(self.n_replicas)
            ]
        return [(i, [RoleJudge(r, self.horizon)]) for i, r in enumerate(ROLES)]

    def state_for(self, sample: Sample, stage_index: int) -> State:
        """Indicators computed from the stored bars; D sends one role's keys."""
        closes = sample.state["bars"]
        if self.arm == "D":
            return role_state(closes, ROLES[stage_index])
        return all_state(closes)

    def judge_for(self, judge_id: str) -> Judge:
        """Rebuild the Judge named by a stored id."""
        return judge_from_id(judge_id, self.horizon)


def n_expected(arm: str, n_replicas: int) -> int:
    """Number of Judge answers expected per sample for an arm."""
    if arm in ("A", "Ap"):
        return 1
    if arm in ("C", "Ap5"):
        return n_replicas
    if arm == "D":
        return len(ROLES)
    raise ValueError(f"unknown arm: {arm!r}")


def arm_spec(study_id: str, arm: str, n_replicas: int, horizon: int) -> ArmLike:
    """Build the spec of any Experiment 1 or 2 arm."""
    if arm == "A":
        return ArmSpec(
            study_id=study_id, arm="A", n_replicas=n_replicas, horizon=horizon
        )
    if arm == "C":
        return ArmSpec(
            study_id=study_id,
            arm="C",
            topology="batched",
            n_replicas=n_replicas,
            horizon=horizon,
        )
    if arm in ("Ap", "Ap5", "D"):
        return Exp2ArmSpec(
            study_id=study_id, arm=arm, n_replicas=n_replicas, horizon=horizon
        )
    raise ValueError(f"unknown arm: {arm!r}")
