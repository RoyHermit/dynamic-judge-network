"""Runner topologies, resumability and failure handling (spec §5.3, §9)."""

import pytest
import typesafe_sdk as ts

from src.data.synthetic import SyntheticConfig, SyntheticSource
from src.experiments.runner import ArmSpec, finish_pending_interpretations, run_arm
from src.judges.interface import Answer, CallRecord, Question, RawJudgeRecord
from src.judges.jev_executor import JevStageExecutor
from src.storage import db
from src.storage.writer import SqliteStorageWriter


class FakeJevClient:
    def __init__(self, p=0.7, fail=False, drop=()):
        self.p, self.fail, self.drop = p, fail, set(drop)
        self.requests: list[list[str]] = []

    async def system_one(self, *, state, questions, **kwargs):
        self.requests.append(list(questions))
        if self.fail:
            raise ts.TypeSafeError("boom")
        return ts.SystemOneResponse(
            model="jev-test",
            usage=ts.Usage(input_tokens=10, output_tokens=2),
            answers={
                name: ts.NoulAnswer(noul=self.p)
                for name in questions
                if name not in self.drop
            },
        )


@pytest.fixture
def samples():
    cfg = SyntheticConfig(
        seed=5,
        split_sizes={"pilot": 4, "calib": 4, "thresh": 4, "test": 4, "test_shift": 4},
    )
    return SyntheticSource(cfg).samples("pilot")[:3]


@pytest.fixture
def env(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    return conn, SqliteStorageWriter(conn)


def _count(conn, sql, *params) -> int:
    return conn.execute(sql, params).fetchone()[0]


def test_experiment_ids_are_distinct_per_arm():
    ids = {
        ArmSpec(study_id="s", arm="A", run=1).experiment_id,
        ArmSpec(study_id="s", arm="A", run=2).experiment_id,
        ArmSpec(study_id="s", arm="C", topology="batched").experiment_id,
        ArmSpec(study_id="s", arm="C", topology="separate").experiment_id,
    }
    assert ids == {"s-A-run1", "s-A-run2", "s-C-batched", "s-C-separate"}


async def test_arm_a_makes_one_call_per_sample(env, samples):
    conn, writer = env
    client = FakeJevClient()
    spec = ArmSpec(study_id="s", arm="A", horizon=5)
    n = await run_arm(spec, samples, JevStageExecutor(client, writer), writer, conn)
    assert n == 3
    assert (
        _count(conn, "SELECT COUNT(*) FROM calls WHERE experiment_id='s-A-run1'") == 3
    )
    assert _count(conn, "SELECT COUNT(*) FROM judge_logs") == 3
    assert _count(conn, "SELECT COUNT(*) FROM inputs") == 3
    assert _count(conn, "SELECT COUNT(*) FROM experiments") == 1


async def test_arm_c_batched_sends_all_replicas_in_one_call(env, samples):
    conn, writer = env
    client = FakeJevClient()
    spec = ArmSpec(study_id="s", arm="C", topology="batched", n_replicas=5, horizon=5)
    await run_arm(spec, samples, JevStageExecutor(client, writer), writer, conn)
    assert _count(conn, "SELECT COUNT(*) FROM calls") == 3
    assert _count(conn, "SELECT COUNT(*) FROM judge_logs") == 15
    assert client.requests[0] == [f"hl_judge#{k}" for k in range(5)]


async def test_arm_c_separate_makes_one_call_per_replica(env, samples):
    conn, writer = env
    client = FakeJevClient()
    spec = ArmSpec(study_id="s", arm="C", topology="separate", n_replicas=5, horizon=5)
    await run_arm(spec, samples, JevStageExecutor(client, writer), writer, conn)
    assert _count(conn, "SELECT COUNT(*) FROM calls") == 15
    stages = {r[0] for r in conn.execute("SELECT DISTINCT stage_index FROM calls")}
    assert stages == {0, 1, 2, 3, 4}


async def test_rerun_executes_nothing_and_max_units_caps_new_work(env, samples):
    conn, writer = env
    executor = JevStageExecutor(FakeJevClient(), writer)
    spec = ArmSpec(study_id="s", arm="C", topology="separate", n_replicas=5, horizon=5)
    assert await run_arm(spec, samples, executor, writer, conn, max_units=4) == 4
    assert await run_arm(spec, samples, executor, writer, conn) == 11
    assert await run_arm(spec, samples, executor, writer, conn) == 0
    assert _count(conn, "SELECT COUNT(*) FROM calls") == 15


async def test_failed_calls_are_terminal_and_not_retried(env, samples):
    conn, writer = env
    executor = JevStageExecutor(FakeJevClient(fail=True), writer)
    spec = ArmSpec(study_id="s", arm="A", horizon=5)
    assert await run_arm(spec, samples, executor, writer, conn) == 3
    assert _count(conn, "SELECT COUNT(*) FROM calls WHERE status='error'") == 3
    assert _count(conn, "SELECT COUNT(*) FROM judge_logs") == 0
    assert await run_arm(spec, samples, executor, writer, conn) == 0


async def test_dropped_answer_leaves_a_missing_replica_row(env, samples):
    conn, writer = env
    client = FakeJevClient(drop={"hl_judge#2"})
    spec = ArmSpec(study_id="s", arm="C", topology="batched", n_replicas=5, horizon=5)
    await run_arm(spec, samples, JevStageExecutor(client, writer), writer, conn)
    assert _count(conn, "SELECT COUNT(*) FROM judge_logs") == 12  # 3 x 4


async def test_pending_interpretations_are_finished_without_new_calls(env):
    conn, writer = env
    call = CallRecord(
        call_id="c1",
        experiment_id="s-A-run1",
        input_id="i1",
        stage_index=0,
        executor="JevStageExecutor",
        question_count=1,
        latency=0.1,
        status="success",
    )
    raw = RawJudgeRecord(
        judge_id="hl_judge",
        judge_version="highlow-1.0",
        judge_prompt_or_definition="d",
        question=Question(kind="noul", prompt="p"),
        raw_answer=Answer(kind="noul", raw_value=0.8, raw_probability=0.8),
        latency=0.1,
    )
    await writer.record_call(call, [raw])
    spec = ArmSpec(study_id="s", arm="A", horizon=5)
    await finish_pending_interpretations(conn, writer, spec)
    value = conn.execute("SELECT interpreted_value FROM judge_logs").fetchone()[0]
    assert value == 0.8


async def test_resuming_with_a_different_data_or_model_config_is_refused(env, samples):
    conn, writer = env
    executor = JevStageExecutor(FakeJevClient(), writer)
    spec = ArmSpec(study_id="s", arm="A", horizon=5)
    extra = {"data": {"seed": 1}, "requested_model": "m1", "extra_body": None}
    await run_arm(spec, samples, executor, writer, conn, config_extra=extra)
    # same identity resumes fine and runs nothing new
    assert await run_arm(spec, samples, executor, writer, conn, config_extra=extra) == 0
    for changed in (
        {**extra, "data": {"seed": 2}},
        {**extra, "requested_model": "m2"},
        {**extra, "extra_body": {"temperature": 1.0}},
    ):
        with pytest.raises(ValueError, match="different"):
            await run_arm(spec, samples, executor, writer, conn, config_extra=changed)
