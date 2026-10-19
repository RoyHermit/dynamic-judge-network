"""Experiment 2 whole pipeline against a seeded fake client (no real API)."""

import asyncio
import json

from helpers_exp2 import RoleClient, small_config

from src.data.factory import load_source
from src.experiments.exp2_arms import arm_spec
from src.experiments.exp2_cli import load_config, load_report, main
from src.experiments.exp2_report import COMPARISONS, LLM_ARMS
from src.experiments.runner import run_arm
from src.judges.jev_executor import JevStageExecutor
from src.storage import db
from src.storage.writer import SqliteStorageWriter

SPLITS = ("pilot", "calib", "thresh", "test", "test_shift")


async def _run_everything(config_path) -> None:
    cfg = load_config(str(config_path))
    source = load_source(cfg.data)
    conn = db.connect(cfg.db_path)
    writer = SqliteStorageWriter(conn)
    executor = JevStageExecutor(RoleClient(), writer)
    for arm in LLM_ARMS:
        spec = arm_spec(cfg.study_id, arm, cfg.n_replicas, cfg.data.horizon)
        for split in SPLITS:
            await run_arm(spec, source.samples(split), executor, writer, conn)
    conn.close()


def test_end_to_end_synthetic_with_fake_client(tmp_path, capsys):
    path = small_config(tmp_path)
    asyncio.run(_run_everything(path))
    cfg = load_config(str(path))

    ids = {
        a: arm_spec(cfg.study_id, a, cfg.n_replicas, 5).experiment_id for a in LLM_ARMS
    }
    # A and C reuse the Experiment 1 specs (and experiment id scheme)
    assert ids["A"] == "exp2-A-run1" and ids["C"] == "exp2-C-batched"
    assert ids["Ap"] == "exp2-Ap" and ids["Ap5"] == "exp2-Ap5" and ids["D"] == "exp2-D"

    main(["pilot-check", "--config", str(path)])  # no stop: returns normally
    check = json.loads(capsys.readouterr().out)
    assert check["stop"] is False
    assert set(check["invalid_rate"]) == set(ids.values())

    for arm in LLM_ARMS:
        main(["fit", "--config", str(path), "--arm", arm])
    main(["fit", "--config", str(path), "--arm", "D"])  # rerun reuses the freeze
    for arm in ("D", "Ap"):
        main(
            ["fit", "--config", str(path), "--arm", arm]
            + ["--decisions-split", "test_shift"]
        )
    capsys.readouterr()

    conn = db.connect(cfg.db_path)
    n_decisions = conn.execute(
        "SELECT COUNT(*) FROM decisions WHERE experiment_id = ?", (ids["D"],)
    ).fetchone()[0]
    assert n_decisions > 0
    conn.close()

    report = load_report(str(path), "test", list(LLM_ARMS), preliminary=False)
    assert set(report["comparisons"]) == set(COMPARISONS)
    assert all(report["comparisons"][k] is not None for k in COMPARISONS)
    verdict = report["verdict"]
    assert set(verdict) >= {"passed", "criteria", "attributable", "notes"}
    assert set(verdict["criteria"]) == {"D>A' (+3pt)", "D>Majority", "D>L", "D>M"}
    assert verdict["attributable"] is not None  # A'x5 was run
    assert report["arms"]["A"]["experiment_id"] == "exp2-A-run1"
    assert report["arms"]["C"]["experiment_id"] == "exp2-C-batched"

    main(["report", "--config", str(path), "--split", "test"])
    assert "D-Ap" in capsys.readouterr().out

    main(["report", "--config", str(path), "--split", "test_shift"])
    out = capsys.readouterr().out
    assert "secondary" in out
    shift = load_report(str(path), "test_shift", list(LLM_ARMS), preliminary=False)
    assert shift["verdict"] is None
    assert set(shift["arms"]) == {"D", "Ap", "L", "M", "Majority"}
