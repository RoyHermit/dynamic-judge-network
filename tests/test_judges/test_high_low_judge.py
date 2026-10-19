"""Tests for HighLowJudge (spec §5.1)."""

import math

import pytest

from src.judges.definitions.high_low import HighLowJudge, replica_index
from src.judges.interface import Answer, Judge


def _noul(p) -> Answer:
    return Answer(kind="noul", raw_value=p if p is not None else 0.0, raw_probability=p)


def test_satisfies_judge_protocol_and_ids():
    assert isinstance(HighLowJudge(horizon=5), Judge)
    assert HighLowJudge(5).judge_id == "hl_judge"
    assert HighLowJudge(5, replica=3).judge_id == "hl_judge#3"
    assert replica_index("hl_judge#3") == 3
    assert replica_index("hl_judge") is None


def test_to_question_is_noul_and_mentions_horizon():
    q = HighLowJudge(horizon=7).to_question({"bars": [1.0, 2.0]})
    assert q.kind == "noul"
    assert "7 bars" in q.prompt


def test_interpret_returns_probability_of_high():
    decision = HighLowJudge(5).interpret(_noul(0.73))
    assert decision.value == 0.73


@pytest.mark.parametrize("bad", [None, math.nan, -0.1, 1.2, math.inf])
def test_interpret_rejects_invalid_probability(bad):
    with pytest.raises(ValueError):
        HighLowJudge(5).interpret(_noul(bad))


def test_interpret_rejects_non_noul_answers():
    answer = Answer(kind="choice", raw_value="HIGH", raw_probability=0.9)
    with pytest.raises(ValueError):
        HighLowJudge(5).interpret(answer)
