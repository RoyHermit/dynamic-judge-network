"""Experiment 2 CLI wrappers: run guard, fit completeness, pilot gate, verdict.

Answers come from a seeded fake client; no real data and no API calls.
"""

import asyncio
import json
from pathlib import Path

import pytest
from helpers_exp2 import (
    SMALL_SIZES,
    RoleClient,
    run_everything,
    small_config,
    write_ecb_csv,
)
from pydantic import ValidationError

from src.data.ecb import EcbCsvConfig
from src.data.factory import load_source
from src.experiments import exp2_cli
from src.experiments.exp2_arms import arm_spec, judge_fingerprint
from src.experiments.exp2_cli import load_config, main
from src.experiments.exp2_report import LLM_ARMS
from src.experiments.runner import run_arm
from src.judges.definitions import indicator_judge
from src.judges.jev_executor import JevStageExecutor
from src.storage import db
from src.storage.reader import load_experiment_config
from src.storage.writer import SqliteStorageWriter


async def _run(path: Path, arm: str, splits: dict[str, int | None], client) -> None:
    """Run `arm` on each split; `splits[split]` caps the number of samples."""
    cfg = load_config(str(path))
    source = load_source(cfg.data)
    conn = db.connect(cfg.db_path)
    writer = SqliteStorageWriter(conn)
    spec = arm_spec(cfg.study_id, arm, cfg.n_replicas, cfg.data.horizon)
    executor = JevStageExecutor(client, writer)
    for split, cap in splits.items():
        samples = source.samples(split)
        await run_arm(spec, samples[:cap], executor, writer, conn)
    conn.close()


def test_cli_run_fails_fast_without_credentials(tmp_path, monkeypatch):
    path = small_config(tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    class NoClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("client must not be constructed")

    monkeypatch.setattr(exp2_cli.ts, "AsyncTypeSafeClient", NoClient)
    with pytest.raises(ValidationError):
        main(["run", "--config", str(path), "--arm", "D", "--split", "pilot"])
    assert not Path(load_config(str(path)).db_path).exists()  # nothing written


async def test_fit_refuses_incomplete_run(tmp_path):
    path = small_config(tmp_path)
    full = {"calib": None, "test": None}
    await _run(path, "Ap", {**full, "thresh": -1}, RoleClient())  # one thresh short
    argv = ["fit", "--config", str(path), "--arm", "Ap"]
    with pytest.raises(ValueError, match="incomplete"):
        await asyncio.to_thread(main, argv)
    conn = db.connect(load_config(str(path)).db_path)
    assert "frozen" not in load_experiment_config(conn, "exp2-Ap")

    await asyncio.to_thread(main, [*argv, "--allow-incomplete"])
    assert "fit" in load_experiment_config(conn, "exp2-Ap")["frozen"]


async def test_fit_refuses_a_different_dataset(tmp_path):
    path = small_config(tmp_path)
    cfg = load_config(str(path))
    source = load_source(cfg.data)
    conn = db.connect(cfg.db_path)
    writer = SqliteStorageWriter(conn)
    spec = arm_spec(cfg.study_id, "Ap", cfg.n_replicas, 5)
    executor = JevStageExecutor(RoleClient(), writer)
    for split in ("calib", "thresh"):
        await run_arm(
            spec,
            source.samples(split),
            executor,
            writer,
            conn,
            config_extra={"dataset_id": "something-else"},
        )
    with pytest.raises(ValueError, match="different dataset"):
        await asyncio.to_thread(main, ["fit", "--config", str(path), "--arm", "Ap"])


async def test_total_calls_per_sample_is_13(tmp_path):
    path = small_config(tmp_path)
    client = RoleClient()
    for arm in LLM_ARMS:
        await _run(path, arm, {"pilot": 1}, client)
    assert len(client.requests) == 13  # A 1 + C 1 + A' 1 + A'x5 5 + D 5 (§9)


async def test_pilot_check_exit_code_on_stop(tmp_path, capsys):
    path = small_config(tmp_path)
    await _run(path, "Ap", {"pilot": None}, RoleClient(constant=0.7))
    argv = ["pilot-check", "--config", str(path), "--arms", "Ap"]  # diagnostic
    with pytest.raises(SystemExit) as exc:
        await asyncio.to_thread(main, argv)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert '"stop": true' in out and "uninformative" in out


def test_pilot_check_stops_when_an_arm_is_missing(tmp_path, capsys):
    path = small_config(tmp_path)
    for arm in ("A", "C", "Ap", "D"):  # Ap5 never ran
        asyncio.run(_run(path, arm, {"pilot": None}, RoleClient()))
    with pytest.raises(SystemExit) as exc:
        main(["pilot-check", "--config", str(path)])
    assert exc.value.code == 1
    check = json.loads(capsys.readouterr().out)
    assert check["stop"] is True
    assert check["reasons"] == ["missing pilot arm exp2-Ap5"]


def test_pilot_check_with_no_arms_stops(tmp_path, capsys):
    path = small_config(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["pilot-check", "--config", str(path)])
    assert exc.value.code == 1
    assert len(json.loads(capsys.readouterr().out)["reasons"]) == len(LLM_ARMS)


def test_pilot_check_passes_with_all_five_healthy_arms(tmp_path, capsys):
    path = small_config(tmp_path)
    for arm in LLM_ARMS:
        asyncio.run(_run(path, arm, {"pilot": None}, RoleClient()))
    main(["pilot-check", "--config", str(path)])  # returns normally: exit 0
    check = json.loads(capsys.readouterr().out)
    assert check["stop"] is False and check["reasons"] == []
    assert len(check["invalid_rate"]) == len(LLM_ARMS)


class _FakeClientContext:
    """Stands in for ts.AsyncTypeSafeClient; yields a fake, never the network."""

    def __init__(self, *args, **kwargs):
        self.client = RoleClient()

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, *exc):
        return False


def test_run_command_wiring_passes_fit_identity_check(tmp_path, monkeypatch):
    path = small_config(tmp_path)
    monkeypatch.setattr(exp2_cli.Settings, "load", classmethod(lambda cls: None))
    monkeypatch.setattr(exp2_cli.ts, "AsyncTypeSafeClient", _FakeClientContext)
    for split in ("calib", "thresh", "test"):
        main(["run", "--config", str(path), "--arm", "Ap", "--split", split])
    conn = db.connect(load_config(str(path)).db_path)
    stored = load_experiment_config(conn, "exp2-Ap")
    assert stored["dataset_id"] and stored["data"]["seed"] == 11
    main(["fit", "--config", str(path), "--arm", "Ap"])
    assert "fit" in load_experiment_config(conn, "exp2-Ap")["frozen"]


async def test_fit_refuses_a_different_replica_count(tmp_path):
    path = small_config(tmp_path)
    await _run(path, "Ap5", {"calib": None, "thresh": None}, RoleClient())
    other = small_config(tmp_path, n_replicas=3)  # same file, same db
    with pytest.raises(ValueError, match="n_replicas"):
        await asyncio.to_thread(main, ["fit", "--config", str(other), "--arm", "Ap5"])


def test_verdict_refuses_swapped_datasets(tmp_path):
    ecb = small_config(tmp_path, name="ecb", data=EcbCsvConfig(path="unused.csv"))
    syn = small_config(tmp_path, name="syn")
    with pytest.raises(ValueError, match="ecb_csv"):
        main(["verdict", "--ecb-config", str(syn), "--synthetic-config", str(syn)])
    with pytest.raises(ValueError, match="synthetic"):
        main(["verdict", "--ecb-config", str(ecb), "--synthetic-config", str(ecb)])


def _canned_verdict(passed: bool, attributable: bool | None) -> dict:
    return {
        "passed": passed,
        "criteria": {"D>A' (+3pt)": passed, "D>Majority": True},
        "attributable": attributable,
        "notes": [],
    }


def test_verdict_command_prints_combined_label(tmp_path, monkeypatch, capsys):
    ecb = small_config(tmp_path, name="ecb", data=EcbCsvConfig(path="unused.csv"))
    syn = small_config(tmp_path, name="syn")
    calls = []

    def fake_load_report(config_path, split, arms, preliminary, **kwargs):
        calls.append((config_path, split, tuple(arms), preliminary))
        return {"verdict": _canned_verdict(config_path == str(ecb), None)}

    monkeypatch.setattr(exp2_cli, "load_report", fake_load_report)
    main(["verdict", "--ecb-config", str(ecb), "--synthetic-config", str(syn)])
    out = capsys.readouterr().out
    assert "Exploratory success" in out  # ECB passes, synthetic fails
    assert "D>A' (+3pt)" in out and "ECB" in out and "synthetic" in out
    assert calls == [
        (str(ecb), "test", tuple(LLM_ARMS), False),
        (str(syn), "test", tuple(LLM_ARMS), False),
    ]


def test_report_requires_ap5_unless_preliminary(tmp_path, monkeypatch):
    path = small_config(tmp_path)
    seen = []

    def fake_build_report(conn, cfg, source, split, arms, *, preliminary=False):
        seen.append((tuple(arms), preliminary))
        return {"verdict": None, "notes": []}

    monkeypatch.setattr(exp2_cli, "build_report", fake_build_report)
    monkeypatch.setattr(exp2_cli, "render_markdown", lambda report: "md")
    monkeypatch.setattr(exp2_cli, "load_frozen_fit", lambda conn, eid: None)
    monkeypatch.setattr(exp2_cli, "_check_complete", lambda *args: None)
    main(["report", "--config", str(path), "--split", "test"])
    main(
        ["report", "--config", str(path), "--split", "test"]
        + ["--arms", "D", "Ap", "--preliminary"]
    )
    assert seen == [(tuple(LLM_ARMS), False), (("D", "Ap"), True)]


def test_resume_after_a_prompt_change_is_refused(tmp_path, monkeypatch):
    path = small_config(tmp_path)
    monkeypatch.setattr(exp2_cli.Settings, "load", classmethod(lambda cls: None))
    monkeypatch.setattr(exp2_cli.ts, "AsyncTypeSafeClient", _FakeClientContext)
    argv = ["run", "--config", str(path), "--arm", "D", "--split", "pilot"]
    main([*argv, "--max-units", "2"])
    conn = db.connect(load_config(str(path)).db_path)
    assert load_experiment_config(conn, "exp2-D")["judge_fingerprint"]
    main(argv)  # same prompts: resuming is allowed

    original = indicator_judge.build_prompt

    def fixed_prompt(role_name: str, keys: tuple[str, ...], horizon: int) -> str:
        return original(role_name, keys, horizon) + " Answer carefully."

    monkeypatch.setattr(indicator_judge, "build_prompt", fixed_prompt)
    with pytest.raises(ValueError, match="judge_fingerprint"):
        main(argv)


def test_judge_fingerprint_tracks_prompt_and_version(monkeypatch):
    spec = arm_spec("s", "Ap", 5, 5)
    base = judge_fingerprint(spec)
    assert base == judge_fingerprint(arm_spec("other-study", "Ap", 5, 5))
    assert base != judge_fingerprint(arm_spec("s", "Ap", 5, 7))  # horizon in prompt
    monkeypatch.setattr(indicator_judge.AllIndicatorsJudge, "judge_version", "x")
    assert judge_fingerprint(spec) != base


def _fit_all(path: Path) -> None:
    for arm in LLM_ARMS:
        main(["fit", "--config", str(path), "--arm", arm])


def test_report_refuses_an_incomplete_test_split(tmp_path, capsys):
    path = small_config(tmp_path)
    asyncio.run(run_everything(path, short={("D", "test"): 1}))
    _fit_all(path)
    capsys.readouterr()
    argv = ["report", "--config", str(path), "--split", "test"]
    with pytest.raises(ValueError, match="incomplete: 5 test units"):
        main(argv)
    main([*argv, "--allow-incomplete"])
    out = capsys.readouterr().out
    assert "incomplete run: arm D has 5 test units without a recorded call" in out


def test_report_refuses_an_unfitted_arm(tmp_path):
    path = small_config(tmp_path)
    asyncio.run(run_everything(path))
    for arm in ("A", "C", "Ap", "D"):  # Ap5 never fitted
        main(["fit", "--config", str(path), "--arm", arm])
    with pytest.raises(ValueError, match="no frozen fit"):
        main(["report", "--config", str(path), "--allow-incomplete"])


def test_verdict_refuses_incomplete_and_prints_context(tmp_path, capsys):
    csv = write_ecb_csv(tmp_path / "rates.csv")
    ecb_data = EcbCsvConfig(path=str(csv), split_sizes=dict(SMALL_SIZES))
    ecb = small_config(tmp_path, name="ecb", data=ecb_data)
    syn = small_config(tmp_path, name="syn")
    asyncio.run(run_everything(ecb, short={("Ap", "test"): 1}))
    asyncio.run(run_everything(syn))
    _fit_all(ecb)
    _fit_all(syn)
    capsys.readouterr()
    argv = ["verdict", "--ecb-config", str(ecb), "--synthetic-config", str(syn)]
    with pytest.raises(ValueError, match="incomplete"):
        main(argv)
    main([*argv, "--allow-incomplete"])
    out = capsys.readouterr().out
    assert "Verdict:" in out
    assert "incomplete run: arm Ap has 1 test units" in out
    assert out.count("eligibility n: ") == 2
    for arm in LLM_ARMS:
        assert f"arm {arm}: invalid rate " in out
    assert "Platt fallback" in out


def test_report_json_prints_the_full_report(tmp_path, capsys):
    path = small_config(tmp_path)
    asyncio.run(run_everything(path))
    _fit_all(path)
    capsys.readouterr()
    main(["report", "--config", str(path), "--split", "test", "--json"])
    report = json.loads(capsys.readouterr().out)
    d = report["arms"]["D"]
    assert {"targets", "reliability", "cost", "latency_p95", "platt"} <= set(d)
    assert report["diagnostics"]["correlation"]["D"] is not None
