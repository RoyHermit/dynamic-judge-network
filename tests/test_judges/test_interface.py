"""Unit tests for the Judge/executor/storage contract types.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §3.
"""

import pytest
from pydantic import ValidationError

from src.judges.interface import Answer, CallRecord, Decision, Question


def test_choice_question_requires_options():
    with pytest.raises(ValidationError):
        Question(kind="choice", prompt="pick one")


def test_choice_question_with_options_is_valid():
    question = Question(kind="choice", prompt="pick one", options=["HIGH", "LOW"])
    assert question.options == ["HIGH", "LOW"]


def test_score_question_rejects_options():
    with pytest.raises(ValidationError):
        Question(kind="score", prompt="rate it", options=["HIGH", "LOW"])


def test_noul_question_rejects_options():
    with pytest.raises(ValidationError):
        Question(kind="noul", prompt="true or false?", options=["yes"])


def test_answer_accepts_bool_raw_value_for_noul():
    answer = Answer(kind="noul", raw_value=True, raw_probability=0.9)
    assert answer.raw_value is True


def test_decision_confidence_and_evidence_are_optional():
    decision = Decision(value="HIGH")
    assert decision.confidence is None
    assert decision.evidence is None


def test_call_record_requires_status_literal():
    with pytest.raises(ValidationError):
        CallRecord(
            call_id="c1",
            experiment_id="e1",
            input_id="i1",
            stage_index=0,
            executor="JevStageExecutor",
            question_count=1,
            latency=0.1,
            status="pending",
        )


def test_judge_protocol_is_structurally_checkable():
    from src.judges.interface import Judge

    class MinimalJudge:
        judge_id = "j1"
        judge_version = "1.0"
        judge_prompt_or_definition = "minimal"

        def to_question(self, state) -> Question:
            return Question(kind="score", prompt="x")

        def interpret(self, answer: Answer) -> Decision:
            return Decision(value=answer.raw_value)

    assert isinstance(MinimalJudge(), Judge)
