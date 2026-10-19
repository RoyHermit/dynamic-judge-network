import math

import pytest

from src.features.indicators import ALL_KEYS, ROLE_INDICATORS
from src.judges.definitions.high_low import HighLowJudge
from src.judges.definitions.indicator_judge import (
    AllIndicatorsJudge,
    RoleJudge,
    judge_from_id,
)
from src.judges.interface import Answer


def test_prompts_identical_except_role_and_keys() -> None:
    role = RoleJudge("trend", 5).to_question({}).prompt
    allj = AllIndicatorsJudge(5).to_question({}).prompt
    role_keys = ", ".join(ROLE_INDICATORS["trend"])
    normalised = role.replace("trend", "@ROLE@", 1).replace(role_keys, "@KEYS@")
    expected = allj.replace(
        "trend, momentum, mean-reversion, volatility and breakout", "@ROLE@"
    ).replace(", ".join(ALL_KEYS), "@KEYS@")
    assert normalised == expected
    assert "the indicators in the state" in role
    assert "5 bars after" in role


def test_judge_ids_and_replicas() -> None:
    assert RoleJudge("trend", 5).judge_id == "role_trend"
    assert RoleJudge("trend", 5).judge_version == "role-1.0"
    assert AllIndicatorsJudge(5).judge_id == "ap_judge"
    assert AllIndicatorsJudge(5, 3).judge_id == "ap_judge#3"
    assert AllIndicatorsJudge(5).judge_version == "allind-1.0"
    assert judge_from_id("role_mean_reversion", 5).judge_id == "role_mean_reversion"
    assert judge_from_id("ap_judge", 5).judge_id == "ap_judge"
    assert judge_from_id("ap_judge#3", 5).judge_id == "ap_judge#3"
    assert judge_from_id("hl_judge", 5).judge_id == "hl_judge"
    hl = judge_from_id("hl_judge#2", 5)
    assert isinstance(hl, HighLowJudge) and hl.judge_id == "hl_judge#2"
    for bad in ("nope", "role_bogus", "ap_judge#x"):
        with pytest.raises(ValueError):
            judge_from_id(bad, 5)


@pytest.mark.parametrize("p", [None, math.nan, 1.5])
def test_interpret_rejects_invalid(p) -> None:
    j = RoleJudge("trend", 5)
    with pytest.raises(ValueError):
        j.interpret(Answer(kind="noul", raw_value=0.5, raw_probability=p))
    with pytest.raises(ValueError):
        j.interpret(Answer(kind="score", raw_value=0.5, raw_probability=0.5))


@pytest.mark.parametrize("p", [0.0, 1.0])
def test_interpret_accepts_bounds(p: float) -> None:
    ans = Answer(kind="noul", raw_value=p, raw_probability=p)
    assert AllIndicatorsJudge(5).interpret(ans).value == p


def test_interpret_rejects_bool_probability() -> None:
    # pydantic coerces True to 1.0, so bypass validation to hit the guard
    ans = Answer.model_construct(kind="noul", raw_value=True, raw_probability=True)
    with pytest.raises(ValueError):
        RoleJudge("trend", 5).interpret(ans)
