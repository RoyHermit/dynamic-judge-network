"""Experiment 2 CLI wrappers: run guard, fit completeness, pilot gate, verdict.

Answers come from a seeded fake client; no real data and no API calls.
"""

import asyncio
from pathlib import Path

import pytest
from helpers_exp2 import RoleClient, small_config
from pydantic import ValidationError

from src.data.factory import load_source
from src.experiments import exp2_cli
from src.experiments.exp2_arms import arm_spec
from src.experiments.exp2_cli import load_config, main
from src.experiments.exp2_report import LLM_ARMS
from src.experiments.runner import run_arm
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
    with pytest.raises(SystemExit) as exc:
        await asyncio.to_thread(main, ["pilot-check", "--config", str(path)])
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert '"stop": true' in out and "uninformative" in out


def test_pilot_check_only_includes_stored_arms(tmp_path, capsys):
    path = small_config(tmp_path)
    asyncio.run(_run(path, "D", {"pilot": None}, RoleClient()))
    main(["pilot-check", "--config", str(path)])
    out = capsys.readouterr().out
    assert '"exp2-D"' in out and '"exp2-Ap"' not in out


def _canned_verdict(passed: bool, attributable: bool | None) -> dict:
    return {
        "passed": passed,
        "criteria": {"D>A' (+3pt)": passed, "D>Majority": True},
        "attributable": attributable,
        "notes": [],
    }


def test_verdict_command_prints_combined_label(tmp_path, monkeypatch, capsys):
    ecb = small_config(tmp_path, name="ecbish")
    syn = small_config(tmp_path, name="syn")
    calls = []

    def fake_build_report(conn, cfg, source, split, arms, *, preliminary=False):
        calls.append((cfg.study_id, split, tuple(arms), preliminary))
        passed = cfg.study_id == "ecbish"
        return {"verdict": _canned_verdict(passed, None)}

    monkeypatch.setattr(exp2_cli, "build_report", fake_build_report)
    main(["verdict", "--ecb-config", str(ecb), "--synthetic-config", str(syn)])
    out = capsys.readouterr().out
    assert "Exploratory success" in out  # ECB passes, synthetic fails
    assert "D>A' (+3pt)" in out and "ECB" in out and "synthetic" in out
    assert calls == [
        ("ecbish", "test", tuple(LLM_ARMS), False),
        ("syn", "test", tuple(LLM_ARMS), False),
    ]


def test_report_requires_ap5_unless_preliminary(tmp_path, monkeypatch):
    path = small_config(tmp_path)
    seen = []

    def fake_build_report(conn, cfg, source, split, arms, *, preliminary=False):
        seen.append((tuple(arms), preliminary))
        return {"verdict": None}

    monkeypatch.setattr(exp2_cli, "build_report", fake_build_report)
    monkeypatch.setattr(exp2_cli, "render_markdown", lambda report: "md")
    main(["report", "--config", str(path), "--split", "test"])
    main(
        ["report", "--config", str(path), "--split", "test"]
        + ["--arms", "D", "Ap", "--preliminary"]
    )
    assert seen == [(tuple(LLM_ARMS), False), (("D", "Ap"), True)]
