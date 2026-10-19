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
from src.data.schema import SPLITS
from src.data.synthetic import SyntheticSource
from src.experiments.config import Exp1Config
from src.experiments.pilot import collect_replica_probs, pilot_stats
from src.experiments.runner import ArmSpec, run_arm
from src.judges.jev_executor import JevStageExecutor
from src.storage import db
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

    args = parser.parse_args(argv)
    if args.command == "run":
        asyncio.run(_run(args))
    elif args.command == "pilot-stats":
        _pilot_stats(args)


if __name__ == "__main__":
    main()
