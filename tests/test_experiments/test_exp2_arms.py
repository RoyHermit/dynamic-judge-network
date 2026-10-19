"""Experiment 2 arm specs through the generalised runner (spec sections 3, 4)."""

import pytest
import typesafe_sdk as ts

from src.data.synthetic import SyntheticConfig, SyntheticSource
from src.experiments.exp2_arms import Exp2ArmSpec, arm_spec, n_expected
from src.experiments.runner import ArmSpec, finish_pending_interpretations, run_arm
from src.features.indicators import ALL_KEYS, ROLE_INDICATORS, ROLES
from src.judges.jev_executor import JevStageExecutor
from src.storage import db
from src.storage.writer import SqliteStorageWriter


class RecordingClient:
    def __init__(self, p: float = 0.7) -> None:
        self.p = p
        self.requests: list[tuple[list[str], dict]] = []

    async def system_one(self, *, state, questions, **kwargs):
        self.requests.append((list(questions), state))
        return ts.SystemOneResponse(
            model="jev-test",
            usage=ts.Usage(input_tokens=10, output_tokens=2),
            answers={name: ts.NoulAnswer(noul=self.p) for name in questions},
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


async def test_d_sends_five_separate_requests_with_only_role_keys(env, samples):
    conn, writer = env
    client = RecordingClient()
    spec = arm_spec("s", "D", 5, 5)
    await run_arm(spec, samples[:1], JevStageExecutor(client, writer), writer, conn)
    assert len(client.requests) == 5
    seen: set[str] = set()
    for questions, state in client.requests:
        assert len(questions) == 1 and questions[0].startswith("role_")
        role = questions[0][len("role_") :]
        assert set(state) == set(ROLE_INDICATORS[role])
        assert "bars" not in state
        seen |= set(state)
    assert seen == set(ALL_KEYS)
    assert {q[0] for q, _ in client.requests} == {f"role_{r}" for r in ROLES}


async def test_ap_state_is_union_and_ap5_is_five_requests(env, samples):
    conn, writer = env
    client = RecordingClient()
    ex = JevStageExecutor(client, writer)
    await run_arm(arm_spec("s", "Ap", 5, 5), samples[:1], ex, writer, conn)
    assert len(client.requests) == 1
    assert client.requests[0][0] == ["ap_judge"]
    assert set(client.requests[0][1]) == set(ALL_KEYS)

    client5 = RecordingClient()
    ex5 = JevStageExecutor(client5, writer)
    await run_arm(arm_spec("s", "Ap5", 5, 5), samples[:1], ex5, writer, conn)
    assert [q for q, _ in client5.requests] == [[f"ap_judge#{k}"] for k in range(5)]


async def test_states_are_pure_function_of_stored_bars(env, samples):
    conn, writer = env
    states = []
    for study in ("s1", "s2"):
        client = RecordingClient()
        await run_arm(
            arm_spec(study, "D", 5, 5),
            samples[:1],
            JevStageExecutor(client, writer),
            writer,
            conn,
        )
        states.append([s for _, s in client.requests])
    assert states[0] == states[1]


async def test_resume_skips_completed_stage(env, samples):
    conn, writer = env
    client = RecordingClient()
    ex = JevStageExecutor(client, writer)
    spec = arm_spec("s", "D", 5, 5)
    assert await run_arm(spec, samples, ex, writer, conn, max_units=2) == 2
    assert await run_arm(spec, samples, ex, writer, conn) == 5 * len(samples) - 2
    assert _count(conn, "SELECT COUNT(*) FROM calls") == 5 * len(samples)
    assert len(client.requests) == 5 * len(samples)


async def test_pending_interpretation_uses_judge_for(env, samples):
    conn, writer = env
    client = RecordingClient(p=0.7)
    spec = arm_spec("s", "D", 5, 5)
    await run_arm(spec, samples[:1], JevStageExecutor(client, writer), writer, conn)
    row = conn.execute(
        "SELECT rowid FROM judge_logs WHERE judge_id='role_trend'"
    ).fetchone()
    assert row is not None
    conn.execute(
        "UPDATE judge_logs SET interpreted_value=NULL WHERE judge_id='role_trend'"
    )
    conn.commit()
    n_requests = len(client.requests)
    await finish_pending_interpretations(conn, writer, spec)
    value = conn.execute(
        "SELECT interpreted_value FROM judge_logs WHERE judge_id='role_trend'"
    ).fetchone()[0]
    assert value == pytest.approx(0.7)
    assert len(client.requests) == n_requests


async def test_identity_mismatch_refuses_resume(env, samples):
    conn, writer = env
    ex = JevStageExecutor(RecordingClient(), writer)
    spec = arm_spec("s", "D", 5, 5)
    await run_arm(
        spec,
        samples,
        ex,
        writer,
        conn,
        max_units=1,
        config_extra={"requested_model": "m1"},
    )
    with pytest.raises(ValueError, match="different"):
        await run_arm(
            spec, samples, ex, writer, conn, config_extra={"requested_model": "m2"}
        )


def test_n_expected():
    assert n_expected("A", 5) == 1
    assert n_expected("Ap", 5) == 1
    assert n_expected("C", 5) == 5
    assert n_expected("Ap5", 5) == 5
    assert n_expected("D", 5) == 5


def test_arm_spec_dispatch_and_ids():
    assert isinstance(arm_spec("s", "A", 5, 5), ArmSpec)
    c = arm_spec("s", "C", 5, 5)
    assert isinstance(c, ArmSpec) and c.topology == "batched"
    ids = {
        a: Exp2ArmSpec(study_id="s", arm=a).experiment_id for a in ("Ap", "Ap5", "D")
    }
    assert ids == {"Ap": "s-Ap", "Ap5": "s-Ap5", "D": "s-D"}
