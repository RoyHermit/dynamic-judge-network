"""Pilot stop-rule checks (spec section 9)."""

import math

import pytest
from helpers_exp1 import insert_judge_log

from src.data.schema import Sample
from src.experiments.exp2_config import Exp2Config
from src.experiments.exp2_pilot import pilot_check
from src.storage import db
from src.storage.writer import SqliteStorageWriter

ROLES = ["role_trend", "role_volatility", "role_reversion", "role_momentum"]
EID = "p1"
CFG = Exp2Config()


def _bars(n: int = 60) -> list[float]:
    return [100.0 + math.sin(i / 3) + i * 0.1 for i in range(n)]


def _sample(iid: str, bars: list[float] | None = None) -> Sample:
    return Sample(
        input_id=iid,
        state={"bars": bars if bars is not None else _bars()},
        label="HIGH",
        split="pilot",
        regime="trend",
        t_index=0,
    )


@pytest.fixture
async def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    await SqliteStorageWriter(c).record_experiment(EID, {"a": 1})
    return c


def _fill(conn, samples, n_invalid=0, constant_role=None) -> None:
    """Varying probabilities per sample; the first n_invalid get a missing judge."""
    for i, s in enumerate(samples):
        for k, j in enumerate(ROLES):
            if i < n_invalid and k == 0:
                continue
            v = 0.3 if j == constant_role else 0.1 + 0.8 * ((i * (k + 3)) % 10) / 10
            insert_judge_log(
                conn, EID, s.input_id, j, value=v, call_id=f"{s.input_id}-{j}"
            )


def _pilot(n: int = 30) -> list[Sample]:
    return [_sample(f"s{i}") for i in range(n)]


def test_invalid_rate_above_five_percent_stops(conn):
    pilot = _pilot()
    _fill(conn, pilot, n_invalid=2)
    r = pilot_check(conn, {EID: 4}, pilot, CFG)
    assert r.stop and r.invalid_rate[EID] == pytest.approx(2 / 30)
    assert any("invalid" in x for x in r.reasons)


def test_invalid_rate_at_one_of_thirty_does_not_stop(conn):
    pilot = _pilot()
    _fill(conn, pilot, n_invalid=1)
    r = pilot_check(conn, {EID: 4}, pilot, CFG)
    assert not r.stop and r.invalid_rate[EID] == pytest.approx(1 / 30)


def test_constant_judge_probability_stops_and_names_role(conn):
    pilot = _pilot()
    _fill(conn, pilot, constant_role="role_trend")
    r = pilot_check(conn, {EID: 4}, pilot, CFG)
    assert r.stop
    assert r.uninformative_roles == ["role_trend"]
    assert r.judge_std[f"{EID}:role_trend"] == 0.0
    assert any("role_trend" in x for x in r.reasons)


def test_nonfinite_indicator_stops(conn):
    pilot = _pilot()
    bars = _bars()
    bars[10] = 0.0
    pilot[3] = _sample("s3", bars)
    _fill(conn, pilot)
    r = pilot_check(conn, {EID: 4}, pilot, CFG)
    assert r.stop
    assert any("indicator" in x for x in r.reasons)


def test_wrong_length_bars_stop_not_crash(conn):
    pilot = _pilot()
    pilot[0] = _sample("s0", _bars(10))
    _fill(conn, pilot)
    assert pilot_check(conn, {EID: 4}, pilot, CFG).stop


def test_healthy_pilot_does_not_stop(conn):
    pilot = _pilot()
    _fill(conn, pilot)
    r = pilot_check(conn, {EID: 4}, pilot, CFG)
    assert not r.stop and r.reasons == [] and r.uninformative_roles == []
    assert r.invalid_rate[EID] == 0.0


def test_only_pilot_inputs_count(conn):
    pilot = _pilot()
    _fill(conn, pilot)
    insert_judge_log(conn, EID, "other", "role_trend", value=0.5, call_id="o1")
    r = pilot_check(conn, {EID: 4}, pilot, CFG)
    assert not r.stop


def test_single_value_judge_has_none_std_and_is_not_flagged(conn):
    pilot = _pilot(1)
    _fill(conn, pilot)
    r = pilot_check(conn, {EID: 4}, pilot, CFG)
    assert r.judge_std[f"{EID}:role_trend"] is None
    assert r.uninformative_roles == []


def test_empty_pilot_raises(conn):
    with pytest.raises(ValueError):
        pilot_check(conn, {EID: 4}, [], CFG)
