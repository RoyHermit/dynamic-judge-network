"""Tests for JevStageExecutor. Never calls the real Jev API — see
docs/superpowers/specs/2026-09-27-project-foundation-design.md §8."""

import pytest
import typesafe_sdk as ts

from src.judges.interface import Answer, CallRecord, Decision, Question, StageResult
from src.judges.jev_executor import JevStageExecutor


class FakeJudge:
    def __init__(self, judge_id: str, kind: str = "choice", raises: bool = False):
        self.judge_id = judge_id
        self.judge_version = "test-1.0"
        self.judge_prompt_or_definition = f"fake judge {judge_id}"
        self._kind = kind
        self._raises = raises

    def to_question(self, state) -> Question:
        if self._kind == "choice":
            return Question(
                kind="choice", prompt="HIGH or LOW?", options=["HIGH", "LOW"]
            )
        if self._kind == "score":
            return Question(kind="score", prompt="rate 0-1")
        return Question(kind="noul", prompt="is this true?")

    def interpret(self, answer: Answer) -> Decision:
        if self._raises:
            raise RuntimeError("boom")
        if answer.kind == "noul":
            p = answer.raw_probability
            value = p >= 0.5
            confidence = p if value else 1 - p
            return Decision(value=value, confidence=confidence)
        return Decision(value=answer.raw_value, confidence=answer.raw_probability)


class FakeWriter:
    def __init__(self):
        self.events: list[tuple] = []

    async def record_call(self, call, raw_judge_records):
        self.events.append(("record_call", call.call_id, call.status))

    async def record_interpretation(self, call_id, judge_id, decision, error):
        self.events.append(
            ("record_interpretation", call_id, judge_id, error is not None)
        )


class FakeClient:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error

    async def system_one(self, *, state, questions):
        if self._error is not None:
            raise self._error
        return self._response


async def test_run_stage_records_call_before_interpret():
    response = ts.SystemOneResponse(
        model="jev-1",
        usage=ts.Usage(input_tokens=10, output_tokens=0),
        answers={
            "j1": ts.ChoiceAnswer(
                choice="HIGH", confidence=0.8, probabilities={"HIGH": 0.8, "LOW": 0.2}
            )
        },
    )
    writer = FakeWriter()
    executor = JevStageExecutor(FakeClient(response=response), writer)

    result = await executor.run_stage(
        state={},
        judges=[FakeJudge("j1")],
        experiment_id="e1",
        input_id="i1",
        stage_index=0,
    )

    assert result.decisions["j1"].value == "HIGH"
    assert [e[0] for e in writer.events] == ["record_call", "record_interpretation"]


async def test_run_stage_records_error_call_on_provider_failure():
    writer = FakeWriter()
    # TypeSafeRateLimitError's real constructor needs a status/body/headers
    # triple normally built from an httpx response; the base TypeSafeError
    # is what the executor actually catches (ts.TypeSafeError), so it's
    # the honest minimal fake for "the provider call failed".
    executor = JevStageExecutor(
        FakeClient(error=ts.TypeSafeError("rate limited")), writer
    )

    result = await executor.run_stage(
        state={},
        judges=[FakeJudge("j1")],
        experiment_id="e1",
        input_id="i1",
        stage_index=0,
    )

    assert result.decisions == {}
    assert len(result.calls) == 1
    assert result.calls[0].status == "error"
    assert result.calls[0].retry_count is None
    assert writer.events == [("record_call", result.calls[0].call_id, "error")]


async def test_interpret_raising_does_not_lose_already_recorded_call():
    response = ts.SystemOneResponse(
        model="jev-1",
        usage=ts.Usage(input_tokens=10, output_tokens=0),
        answers={
            "good": ts.ChoiceAnswer(
                choice="HIGH", confidence=0.8, probabilities={"HIGH": 0.8, "LOW": 0.2}
            ),
            "bad": ts.ChoiceAnswer(
                choice="LOW", confidence=0.6, probabilities={"HIGH": 0.4, "LOW": 0.6}
            ),
        },
    )
    writer = FakeWriter()
    executor = JevStageExecutor(FakeClient(response=response), writer)
    judges = [FakeJudge("good"), FakeJudge("bad", raises=True)]

    result = await executor.run_stage(
        state={}, judges=judges, experiment_id="e1", input_id="i1", stage_index=0
    )

    assert "good" in result.decisions
    assert "bad" not in result.decisions
    call_event = next(e for e in writer.events if e[0] == "record_call")
    assert call_event[2] == "success"
    interpret_events = {
        e[2]: e[3] for e in writer.events if e[0] == "record_interpretation"
    }
    assert interpret_events == {"good": False, "bad": True}


async def test_duplicate_judge_id_raises_value_error():
    executor = JevStageExecutor(FakeClient(), FakeWriter())

    with pytest.raises(ValueError):
        await executor.run_stage(
            state={},
            judges=[FakeJudge("dup"), FakeJudge("dup")],
            experiment_id="e1",
            input_id="i1",
            stage_index=0,
        )


async def test_noul_confidence_reports_confidence_in_reported_verdict_not_raw_p():
    response = ts.SystemOneResponse(
        model="jev-1",
        usage=ts.Usage(input_tokens=5, output_tokens=0),
        answers={"j1": ts.NoulAnswer(noul=0.1)},
    )
    writer = FakeWriter()
    executor = JevStageExecutor(FakeClient(response=response), writer)

    result = await executor.run_stage(
        state={},
        judges=[FakeJudge("j1", kind="noul")],
        experiment_id="e1",
        input_id="i1",
        stage_index=0,
    )

    decision = result.decisions["j1"]
    assert decision.value is False
    assert decision.confidence == pytest.approx(0.9)


class FakeNonBatchingExecutor:
    """Test double proving StageResult.calls need not be exactly one entry
    (spec §3/§8: 'never assumed to be exactly one')."""

    def __init__(self, writer):
        self._writer = writer

    async def run_stage(self, state, judges, *, experiment_id, input_id, stage_index):
        calls: list[CallRecord] = []
        decisions: dict[str, Decision] = {}
        for judge in judges:
            question = judge.to_question(state)
            answer = Answer(kind=question.kind, raw_value="LOW", raw_probability=0.5)
            call = CallRecord(
                call_id=f"call-{judge.judge_id}",
                experiment_id=experiment_id,
                input_id=input_id,
                stage_index=stage_index,
                executor="FakeNonBatchingExecutor",
                question_count=1,
                latency=0.001,
                retry_count=None,
                token_usage=None,
                status="success",
                error_message=None,
            )
            await self._writer.record_call(call, [])
            decisions[judge.judge_id] = judge.interpret(answer)
            calls.append(call)
        return StageResult(decisions=decisions, calls=calls)


async def test_non_batching_executor_returns_one_call_record_per_judge():
    writer = FakeWriter()
    executor = FakeNonBatchingExecutor(writer)
    judges = [FakeJudge("a"), FakeJudge("b"), FakeJudge("c")]

    result = await executor.run_stage(
        state={}, judges=judges, experiment_id="e1", input_id="i1", stage_index=0
    )

    assert len(result.calls) == 3
