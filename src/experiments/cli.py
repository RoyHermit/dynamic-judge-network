"""Thin command-line entry points: run, pilot-stats, report.

`run` calls the real Jev API and spends money; it is human-only (Task 13).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import typesafe_sdk as ts

from src.config import Settings
from src.data.baselines import (
    accuracy,
    fit_momentum,
    fit_regime_aware,
    majority_label,
)
from src.data.schema import SPLITS
from src.data.synthetic import SyntheticSource
from src.experiments.config import Exp1Config
from src.experiments.pilot import collect_replica_probs, pilot_stats
from src.experiments.pipeline import ArmFit, score_rows
from src.experiments.runner import ArmSpec, run_arm
from src.judges.jev_executor import JevStageExecutor
from src.metrics.report import compare_arms, render_markdown
from src.storage import db
from src.storage.reader import load_calls
from src.storage.writer import SqliteStorageWriter


def _load(path: str) -> Exp1Config:
    return Exp1Config.model_validate_json(Path(path).read_text())


async def _run(args: argparse.Namespace) -> None:
    cfg = _load(args.config)
    source = SyntheticSource(cfg.data)
    spec = ArmSpec(
        study_id=cfg.study_id,
        arm=args.arm,
        topology=args.topology,
        run=args.run,
        n_replicas=cfg.n_replicas,
        horizon=cfg.data.horizon,
    )
    Path(cfg.db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(cfg.db_path)
    writer = SqliteStorageWriter(conn)
    extra = {
        "data": cfg.data.model_dump(),
        "excluded": source.data.excluded,
        "requested_model": cfg.model,
        "extra_body": cfg.extra_body,
        "pricing": cfg.pricing.model_dump() if cfg.pricing else None,
    }
    Settings.load()  # fail fast if the credential is missing; value unused
    async with ts.AsyncTypeSafeClient() as client:  # SDK reads it from the environment
        executor = JevStageExecutor(
            client, writer, model=cfg.model, extra_body=cfg.extra_body
        )
        used = await run_arm(
            spec,
            source.samples(args.split),
            executor,
            writer,
            conn,
            config_extra=extra,
            sample_concurrency=cfg.sample_concurrency,
            max_units=args.max_units,
        )
    print(f"{spec.experiment_id}: executed {used} units")


def _pilot_stats(args: argparse.Namespace) -> None:
    cfg = _load(args.config)
    source = SyntheticSource(cfg.data)
    labels = {s.input_id: s.label for s in source.samples("pilot")}
    conn = db.connect(cfg.db_path)
    stats = pilot_stats(collect_replica_probs(conn, args.experiments), labels)
    print(json.dumps(stats.model_dump(), indent=2))


def _report(args: argparse.Namespace) -> None:
    cfg = _load(args.config)
    source = SyntheticSource(cfg.data)
    conn = db.connect(cfg.db_path)

    def frozen_fit(experiment_id: str) -> ArmFit:
        row = conn.execute(
            "SELECT config_json FROM experiments WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        return ArmFit.model_validate(json.loads(row[0])["frozen"]["fit"])

    samples = source.samples(args.split)
    fit_a, fit_c = frozen_fit(args.a_experiment), frozen_fit(args.c_experiment)
    calib = source.samples("calib")
    momentum, regime_aware = fit_momentum(calib), fit_regime_aware(calib)
    references = {
        "majority": accuracy([majority_label(calib)] * len(samples), samples),
        "momentum": accuracy([momentum.predict(s.state) for s in samples], samples),
        "regime_aware": accuracy([regime_aware.predict(s) for s in samples], samples),
    }
    report = compare_arms(
        score_rows(conn, fit_a, samples),
        score_rows(conn, fit_c, samples),
        fit_a,
        fit_c,
        cfg,
        calls_a=load_calls(conn, args.a_experiment),
        calls_c=load_calls(conn, args.c_experiment),
        references=references,
    )
    print(render_markdown(report))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="exp1")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one arm over one split (spends API budget)")
    run.add_argument("--config", required=True)
    run.add_argument("--arm", choices=["A", "C"], required=True)
    run.add_argument("--topology", choices=["batched", "separate"], default="batched")
    run.add_argument("--run", type=int, default=1)
    run.add_argument("--split", choices=list(SPLITS), required=True)
    run.add_argument("--max-units", type=int, default=None)

    ps = sub.add_parser("pilot-stats", help="replica variance for stored experiments")
    ps.add_argument("--config", required=True)
    ps.add_argument("--experiments", nargs="+", required=True)

    rep = sub.add_parser("report", help="compare A and C on one evaluation split")
    rep.add_argument("--config", required=True)
    rep.add_argument("--a-experiment", required=True)
    rep.add_argument("--c-experiment", required=True)
    rep.add_argument("--split", choices=["test", "test_shift"], default="test")

    args = parser.parse_args(argv)
    if args.command == "run":
        asyncio.run(_run(args))
    elif args.command == "pilot-stats":
        _pilot_stats(args)
    elif args.command == "report":
        _report(args)


if __name__ == "__main__":
    main()
