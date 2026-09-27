"""JudgeExecutor that batches Judges belonging to one graph stage into a
single Jev (TypeSafe System One) call — the "speculative fan-out" finding
from docs/superpowers/specs/2026-09-27-project-foundation-design.md §2.

See spec §3 for the full ordering/partial-result contract this
implements.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import typesafe_sdk as ts

from src.judges.interface import (
    Answer,
    CallRecord,
    Decision,
    Judge,
    Question,
    RawJudgeRecord,
    StageResult,
    StorageWriter,
)

_EXECUTOR_NAME = "JevStageExecutor"

_ProviderQuestion = ts.Choice | ts.Score | ts.Noul
_ProviderAnswer = ts.ChoiceAnswer | ts.ScoreAnswer | ts.NoulAnswer


def _to_provider_question(question: Question) -> _ProviderQuestion:
    if question.kind == "choice":
        assert question.options is not None  # enforced by Question itself
        return ts.Choice(
            criteria={option: None for option in question.options},
            instructions=question.prompt,
        )
    if question.kind == "score":
        # Score.criteria (scoring buckets/legend) has no DJN-side shape yet
        # (spec §3.2: State/criteria detail deferred) — empty is the
        # honest minimal translation until a future spec defines buckets.
        return ts.Score(criteria=[], instructions=question.prompt)
    return ts.Noul(instructions=question.prompt)


def _to_dj_answer(provider_answer: _ProviderAnswer) -> Answer:
    if provider_answer.type == "choice":
        return Answer(
            kind="choice",
            raw_value=provider_answer.choice,
            raw_probability=provider_answer.confidence,
        )
    if provider_answer.type == "score":
        return Answer(
            kind="score",
            raw_value=provider_answer.score,
            # ScoreAnswer.confidence is real provider data — passed through
            # raw so a Judge MAY treat it as the "actual, separately-
            # calibrated uncertainty estimate" §3.1 allows; interpret()
            # decides, this layer never fabricates or discards it.
            raw_probability=provider_answer.confidence,
        )
    # NoulAnswer only carries the raw probability — both fields are the
    # same number until interpret() applies §3.1's normalization.
    return Answer(
        kind="noul",
        raw_value=provider_answer.noul,
        raw_probability=provider_answer.noul,
    )


class JevStageExecutor:
    """A JudgeExecutor for Jev-backed Judges (spec §3)."""

    def __init__(self, client: ts.AsyncTypeSafeClient, writer: StorageWriter) -> None:
        self._client = client
        self._writer = writer

    async def run_stage(
        self,
        state: Any,
        judges: list[Judge],
        *,
        experiment_id: str,
        input_id: str,
        stage_index: int,
    ) -> StageResult:
        judge_ids = [judge.judge_id for judge in judges]
        if len(judge_ids) != len(set(judge_ids)):
            raise ValueError(f"duplicate judge_id in stage {stage_index}: {judge_ids}")

        questions = {judge.judge_id: judge.to_question(state) for judge in judges}
        call_id = str(uuid.uuid4())
        start = time.monotonic()

        try:
            response = await self._client.system_one(
                state=state,
                questions={
                    judge_id: _to_provider_question(question)
                    for judge_id, question in questions.items()
                },
            )
        except ts.TypeSafeError as exc:
            latency = time.monotonic() - start
            call = CallRecord(
                call_id=call_id,
                experiment_id=experiment_id,
                input_id=input_id,
                stage_index=stage_index,
                executor=_EXECUTOR_NAME,
                question_count=len(judges),
                latency=latency,
                retry_count=None,
                token_usage=None,
                status="error",
                error_message=str(exc),
            )
            await self._writer.record_call(call, [])
            return StageResult(decisions={}, calls=[call])

        latency = time.monotonic() - start
        token_usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        call = CallRecord(
            call_id=call_id,
            experiment_id=experiment_id,
            input_id=input_id,
            stage_index=stage_index,
            executor=_EXECUTOR_NAME,
            question_count=len(judges),
            latency=latency,
            retry_count=None,
            token_usage=token_usage,
            status="success",
            error_message=None,
        )
        # The SDK silently drops answers it cannot parse, so a judge may be
        # absent from response.answers. Only answered judges get a raw
        # record (and later a decision); the call itself is recorded
        # regardless, since it was already paid for (spec §3).
        answered_judges = [
            judge for judge in judges if judge.judge_id in response.answers
        ]
        raw_records = [
            RawJudgeRecord(
                judge_id=judge.judge_id,
                judge_version=judge.judge_version,
                judge_prompt_or_definition=judge.judge_prompt_or_definition,
                question=questions[judge.judge_id],
                raw_answer=_to_dj_answer(response.answers[judge.judge_id]),
                latency=latency,
            )
            for judge in answered_judges
        ]
        await self._writer.record_call(call, raw_records)

        decisions: dict[str, Decision] = {}
        raw_by_judge_id = {record.judge_id: record for record in raw_records}
        for judge in answered_judges:
            raw_record = raw_by_judge_id[judge.judge_id]
            try:
                decision = judge.interpret(raw_record.raw_answer)
            except Exception as exc:  # noqa: BLE001 — recorded per §3, never re-raised
                await self._writer.record_interpretation(
                    call_id=call_id,
                    judge_id=judge.judge_id,
                    decision=None,
                    error=str(exc),
                )
                continue
            await self._writer.record_interpretation(
                call_id=call_id, judge_id=judge.judge_id, decision=decision, error=None
            )
            decisions[judge.judge_id] = decision

        return StageResult(decisions=decisions, calls=[call])
