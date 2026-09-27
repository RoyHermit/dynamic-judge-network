"""Provider-agnostic contracts for Judges, executors, and storage.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §3.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, model_validator

# State is deliberately unshaped at foundation scope (spec §3.2): its
# concrete structure belongs to the future benchmark data pipeline spec.
State = Any


class Question(BaseModel):
    kind: Literal["choice", "score", "noul"]
    prompt: str
    options: list[str] | None = None

    @model_validator(mode="after")
    def _options_match_kind(self) -> Question:
        if self.kind == "choice" and not self.options:
            raise ValueError("options is required when kind == 'choice'")
        if self.kind != "choice" and self.options is not None:
            raise ValueError("options must be None when kind != 'choice'")
        return self


class Answer(BaseModel):
    kind: Literal["choice", "score", "noul"]
    raw_value: str | float | bool
    raw_probability: float | None = None


class Decision(BaseModel):
    value: str | float | bool
    confidence: float | None = None
    evidence: str | None = None


@runtime_checkable
class Judge(Protocol):
    judge_id: str
    judge_version: str
    judge_prompt_or_definition: str

    def to_question(self, state: State) -> Question: ...

    def interpret(self, answer: Answer) -> Decision: ...


class CallRecord(BaseModel):
    call_id: str
    experiment_id: str
    input_id: str
    stage_index: int
    executor: str
    question_count: int
    latency: float
    retry_count: int | None = None
    token_usage: dict[str, Any] | None = None
    status: Literal["success", "error"]
    error_message: str | None = None


class RawJudgeRecord(BaseModel):
    judge_id: str
    judge_version: str
    judge_prompt_or_definition: str
    question: Question
    raw_answer: Answer
    latency: float


class StageResult(BaseModel):
    decisions: dict[str, Decision]
    calls: list[CallRecord]


@runtime_checkable
class StorageWriter(Protocol):
    async def record_call(
        self, call: CallRecord, raw_judge_records: list[RawJudgeRecord]
    ) -> None: ...

    async def record_interpretation(
        self,
        call_id: str,
        judge_id: str,
        decision: Decision | None,
        error: str | None,
    ) -> None: ...


@runtime_checkable
class JudgeExecutor(Protocol):
    async def run_stage(
        self,
        state: State,
        judges: list[Judge],
        *,
        experiment_id: str,
        input_id: str,
        stage_index: int,
    ) -> StageResult: ...
