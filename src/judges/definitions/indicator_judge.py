"""Indicator Judges for Experiment 2 (spec section 4).

RoleJudge sees one role's indicators; AllIndicatorsJudge (A') sees all of
them. Both build the prompt from one shared helper so the text differs only in
the role name and the key list. The wording is fixed after the pilot.
"""

from __future__ import annotations

from src.features.indicators import ALL_KEYS, ROLE_INDICATORS
from src.judges.definitions.high_low import (
    HighLowJudge,
    parse_probability,
    replica_index,
)
from src.judges.interface import Answer, Decision, Judge, Question, State

ALL_ROLES_NAME = "trend, momentum, mean-reversion, volatility and breakout"


def build_prompt(role_name: str, keys: tuple[str, ...], horizon: int) -> str:
    """Build the shared prompt; only role_name and keys vary between Judges."""
    return (
        f"You are given {role_name} indicators for a price series "
        f"({', '.join(keys)}). "
        f"Using only the indicators in the state, is the close {horizon} bars "
        "after the last bar higher than the last bar's close? Answer with the "
        "probability that it is higher."
    )


class RoleJudge:
    """Judge that reads only the indicators of one role."""

    judge_version = "role-1.0"

    def __init__(self, role: str, horizon: int) -> None:
        if role not in ROLE_INDICATORS:
            raise ValueError(f"unknown role: {role!r}")
        self.role = role
        self.judge_id = f"role_{role}"
        self.judge_prompt_or_definition = build_prompt(
            role.replace("_", "-"), ROLE_INDICATORS[role], horizon
        )

    def to_question(self, state: State) -> Question:
        """Return the fixed Noul question for this role."""
        return Question(kind="noul", prompt=self.judge_prompt_or_definition)

    def interpret(self, answer: Answer) -> Decision:
        """Read the Noul probability as P(HIGH)."""
        return Decision(value=parse_probability(answer))


class AllIndicatorsJudge:
    """A' Judge that reads all indicators at once."""

    judge_version = "allind-1.0"

    def __init__(self, horizon: int, replica: int | None = None) -> None:
        self.judge_id = "ap_judge" if replica is None else f"ap_judge#{replica}"
        self.judge_prompt_or_definition = build_prompt(
            ALL_ROLES_NAME, ALL_KEYS, horizon
        )

    def to_question(self, state: State) -> Question:
        """Return the fixed Noul question over all indicators."""
        return Question(kind="noul", prompt=self.judge_prompt_or_definition)

    def interpret(self, answer: Answer) -> Decision:
        """Read the Noul probability as P(HIGH)."""
        return Decision(value=parse_probability(answer))


def judge_from_id(judge_id: str, horizon: int) -> Judge:
    """Rebuild a Judge from its id (for re-interpreting stored answers)."""
    name = judge_id.partition("#")[0]
    try:
        replica = replica_index(judge_id)
    except ValueError:
        raise ValueError(f"unknown judge id: {judge_id!r}") from None
    if judge_id.startswith("role_") and "#" not in judge_id:
        return RoleJudge(judge_id[len("role_") :], horizon)
    if name == "ap_judge":
        return AllIndicatorsJudge(horizon, replica)
    if name == "hl_judge":
        return HighLowJudge(horizon, replica)
    raise ValueError(f"unknown judge id: {judge_id!r}")
