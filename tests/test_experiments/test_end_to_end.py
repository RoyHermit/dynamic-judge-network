"""Whole pipeline against a state-aware fake client (no real API)."""

import asyncio
import zlib

import pytest
import typesafe_sdk as ts

from src.data.synthetic import SyntheticConfig, SyntheticSource
from src.experiments.config import Exp1Config
from src.experiments.pipeline import fit_arm, score_rows, write_decisions
from src.experiments.runner import ArmSpec, run_arm
from src.judges.jev_executor import JevStageExecutor
from src.metrics.report import compare_arms, render_markdown
from src.storage import db
from src.storage.reader import load_calls
from src.storage.writer import SqliteStorageWriter


class StateAwareClient:
    """P(HIGH) follows a 5-bar momentum signal plus a per-replica jitter."""

    async def system_one(self, *, state, questions, **kwargs):
        bars = state["bars"]
        signal = 1.0 if bars[-1] > bars[-6] else 0.0
        return ts.SystemOneResponse(
            model="jev-test",
            usage=ts.Usage(input_tokens=10, output_tokens=2),
            answers={
                name: ts.NoulAnswer(
                    noul=0.3 + 0.4 * signal + (zlib.crc32(name.encode()) % 7) * 0.01
                )
                for name in questions
            },
        )


class DropFirstReplicaClient(StateAwareClient):
    """Drops replica 0 from every response, so no C sample reaches N answers."""

    async def system_one(self, *, state, questions, **kwargs):
        response = await super().system_one(state=state, questions=questions)
        response.answers.pop("hl_judge#0", None)
        return response


CFG = Exp1Config(
    data=SyntheticConfig(
        seed=7,
        split_sizes={
            "pilot": 5,
            "calib": 60,
            "thresh": 60,
            "test": 60,
            "test_shift": 5,
        },
    ),
    bootstrap_resamples=30,
    bootstrap_block_len=3,
)


async def _run_all(conn, writer, client, specs, source):
    executor = JevStageExecutor(client, writer)
    for spec in specs:
        for split in ("calib", "thresh", "test"):
            await run_arm(spec, source.samples(split), executor, writer, conn)


async def test_pipeline_end_to_end(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    writer = SqliteStorageWriter(conn)
    source = SyntheticSource(CFG.data)
    spec_a = ArmSpec(study_id="e", arm="A", horizon=5)
    spec_c = ArmSpec(study_id="e", arm="C", topology="batched", n_replicas=5, horizon=5)
    await _run_all(conn, writer, StateAwareClient(), [spec_a, spec_c], source)

    calib, thresh, test = (source.samples(s) for s in ("calib", "thresh", "test"))
    fit_a = await fit_arm(conn, writer, spec_a.experiment_id, 1, calib, thresh, CFG)
    fit_c = await fit_arm(conn, writer, spec_c.experiment_id, 5, calib, thresh, CFG)

    with pytest.raises(ValueError):  # frozen settings are never overwritten
        await fit_arm(conn, writer, spec_a.experiment_id, 1, calib, thresh, CFG)

    rows_a, rows_c = score_rows(conn, fit_a, test), score_rows(conn, fit_c, test)
    headline = CFG.target_key(CFG.headline_coverage)
    await write_decisions(conn, writer, fit_c, rows_c, fit_c.margins[headline].margin)
    n_decisions = conn.execute(
        "SELECT COUNT(*) FROM decisions WHERE experiment_id = ?",
        (spec_c.experiment_id,),
    ).fetchone()[0]
    assert n_decisions == sum(r.p is not None for r in rows_c) == len(test)
    used = conn.execute(
        "SELECT COUNT(*) FROM judge_logs WHERE experiment_id = ? AND was_used = 1",
        (spec_c.experiment_id,),
    ).fetchone()[0]
    assert used == 5 * len(test)

    report = compare_arms(
        rows_a,
        rows_c,
        fit_a,
        fit_c,
        CFG,
        calls_a=load_calls(conn, spec_a.experiment_id),
        calls_c=load_calls(conn, spec_c.experiment_id),
    )
    assert report["n_common_valid"] == len(test)
    assert report["warnings"] == []
    assert report["common"]["targets"]["1.00"]["A"]["accuracy"] is not None
    assert "Experiment 1 report" in render_markdown(report)


async def test_dropped_replicas_make_every_c_sample_invalid_but_still_report(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    writer = SqliteStorageWriter(conn)
    source = SyntheticSource(CFG.data)
    spec_a = ArmSpec(study_id="e", arm="A", horizon=5)
    spec_c = ArmSpec(study_id="e", arm="C", topology="batched", n_replicas=5, horizon=5)
    await _run_all(conn, writer, StateAwareClient(), [spec_a], source)
    await _run_all(conn, writer, DropFirstReplicaClient(), [spec_c], source)

    calib, thresh, test = (source.samples(s) for s in ("calib", "thresh", "test"))
    fit_a = await fit_arm(conn, writer, spec_a.experiment_id, 1, calib, thresh, CFG)
    # Every C sample has 4 < N answers: nothing is valid. The fit degrades to
    # an explicit "target not reached" state instead of averaging survivors.
    fit_c = await fit_arm(conn, writer, spec_c.experiment_id, 5, calib, thresh, CFG)
    assert all(not c.reached for c in fit_c.margins.values())

    rows_c = score_rows(conn, fit_c, test)
    assert all(r.p is None for r in rows_c)
    report = compare_arms(
        score_rows(conn, fit_a, test),
        rows_c,
        fit_a,
        fit_c,
        CFG,
        calls_a=load_calls(conn, spec_a.experiment_id),
        calls_c=load_calls(conn, spec_c.experiment_id),
    )
    assert report["n_common_valid"] == 0
    assert report["arms"]["C"]["invalid_rate"] == 1.0
    assert any("arm C" in w for w in report["warnings"])
    assert report["common"]["targets"]["0.80"]["diff_ci"] is None


async def test_report_command_prints_comparison_from_frozen_fits(tmp_path, capsys):
    from src.experiments.cli import main

    cfg = CFG.model_copy(update={"db_path": str(tmp_path / "r.db")})
    config_path = tmp_path / "cfg.json"
    config_path.write_text(cfg.model_dump_json())

    conn = db.connect(cfg.db_path)
    writer = SqliteStorageWriter(conn)
    source = SyntheticSource(cfg.data)
    spec_a = ArmSpec(study_id=cfg.study_id, arm="A", horizon=5)
    spec_c = ArmSpec(study_id=cfg.study_id, arm="C", n_replicas=5, horizon=5)
    await _run_all(conn, writer, StateAwareClient(), [spec_a, spec_c], source)
    calib, thresh = source.samples("calib"), source.samples("thresh")
    await fit_arm(conn, writer, spec_a.experiment_id, 1, calib, thresh, cfg)
    await fit_arm(conn, writer, spec_c.experiment_id, 5, calib, thresh, cfg)
    conn.close()

    main(
        [
            "report",
            "--config",
            str(config_path),
            "--a-experiment",
            spec_a.experiment_id,
            "--c-experiment",
            spec_c.experiment_id,
            "--split",
            "test",
        ]
    )
    out = capsys.readouterr().out
    assert "Experiment 1 report" in out and "majority" in out


async def test_fit_command_freezes_fits_and_writes_decisions(tmp_path):
    from src.experiments.cli import main

    cfg = CFG.model_copy(update={"db_path": str(tmp_path / "f.db")})
    config_path = tmp_path / "cfg.json"
    config_path.write_text(cfg.model_dump_json())
    conn = db.connect(cfg.db_path)
    writer = SqliteStorageWriter(conn)
    source = SyntheticSource(cfg.data)
    spec_c = ArmSpec(study_id=cfg.study_id, arm="C", n_replicas=5, horizon=5)
    await _run_all(conn, writer, StateAwareClient(), [spec_c], source)
    conn.close()

    argv = ["fit", "--config", str(config_path), "--arm", "C"]
    argv += ["--experiment", spec_c.experiment_id]
    # `fit` owns its event loop (asyncio.run), so call it off this loop.
    await asyncio.to_thread(main, argv)

    conn = db.connect(cfg.db_path)
    frozen = conn.execute(
        "SELECT config_json FROM experiments WHERE experiment_id = ?",
        (spec_c.experiment_id,),
    ).fetchone()[0]
    assert '"frozen"' in frozen and '"fit"' in frozen
    n = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    assert n == len(source.samples("test"))
