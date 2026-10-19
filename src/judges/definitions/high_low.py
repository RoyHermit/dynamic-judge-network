"""High/Low Judge for Experiment 1 (spec §5.1).

Asks one Noul question and reads the Noul probability as P(HIGH). Choice
confidence is deliberately not used: it is the confidence of the selected
label, not P(HIGH), so averaging it would be wrong.
"""

from __future__ import annotations

import math

from src.judges.interface import Answer, Decision, Question, State


def replica_index(judge_id: str) -> int | None:
    """Parse `hl_judge#<k>`; return None for the un-replicated Judge."""
    _, sep, tail = judge_id.partition("#")
    return int(tail) if sep else None


def parse_probability(answer: Answer) -> float:
    """Return a valid Noul P(HIGH) from the answer or raise ValueError."""
    p = answer.raw_probability
    if (
        answer.kind != "noul"
        or p is None
        or isinstance(p, bool)
        or not math.isfinite(p)
        or not 0.0 <= p <= 1.0
    ):
        raise ValueError(f"invalid P(HIGH) answer: {answer!r}")
    return p


class HighLowJudge:
    judge_version = "highlow-1.0"

    def __init__(self, horizon: int, replica: int | None = None) -> None:
        self.judge_id = "hl_judge" if replica is None else f"hl_judge#{replica}"
        self.judge_prompt_or_definition = (
            "Using only the price bars in the state (oldest first, the last "
            f"element is the latest close), is the close {horizon} bars after "
            "the last bar higher than the last bar's close? Answer with the "
            "probability that it is higher."
        )

    def to_question(self, state: State) -> Question:
        return Question(kind="noul", prompt=self.judge_prompt_or_definition)

    def interpret(self, answer: Answer) -> Decision:
        return Decision(value=parse_probability(answer))
