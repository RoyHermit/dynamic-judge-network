"""Executor option forwarding and model provenance (spec §3.2, §5.4)."""

import typesafe_sdk as ts

from src.judges.definitions.high_low import HighLowJudge
from src.judges.jev_executor import JevStageExecutor


class CapturingClient:
    def __init__(self) -> None:
        self.kwargs: dict | None = None

    async def system_one(self, **kwargs):
        self.kwargs = kwargs
        return ts.SystemOneResponse(
            model="returned-model",
            usage=ts.Usage(input_tokens=3, output_tokens=1),
            answers={"hl_judge": ts.NoulAnswer(noul=0.6)},
        )


class NullWriter:
    async def record_call(self, call, raw_judge_records):
        pass

    async def record_interpretation(self, call_id, judge_id, decision, error):
        pass


async def test_model_and_extra_body_are_forwarded_and_model_recorded():
    client = CapturingClient()
    executor = JevStageExecutor(
        client, NullWriter(), model="m1", extra_body={"temperature": 1.0}
    )
    result = await executor.run_stage(
        state={"bars": [1.0]},
        judges=[HighLowJudge(5)],
        experiment_id="e",
        input_id="i",
        stage_index=0,
    )
    assert client.kwargs["model"] == "m1"
    assert client.kwargs["extra_body"] == {"temperature": 1.0}
    assert result.calls[0].token_usage == {
        "input_tokens": 3,
        "output_tokens": 1,
        "requested_model": "m1",
        "returned_model": "returned-model",
    }


async def test_options_are_omitted_when_not_set():
    client = CapturingClient()
    executor = JevStageExecutor(client, NullWriter())
    result = await executor.run_stage(
        state={"bars": [1.0]},
        judges=[HighLowJudge(5)],
        experiment_id="e",
        input_id="i",
        stage_index=0,
    )
    assert "model" not in client.kwargs and "extra_body" not in client.kwargs
    assert result.calls[0].token_usage["requested_model"] is None
