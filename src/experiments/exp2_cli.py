"""Experiment 2 command-line entry points (spec §9, §11).

Subcommands: `run` (spends API budget; human-only, never run by agents),
`pilot-check`, `fit`, `report`, `verdict` (all offline). Every function is a
thin wrapper over tested library calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import typesafe_sdk as ts

from src.config import Settings
from src.data.factory import dataset_identity, load_source
from src.data.schema import SPLITS, DataSource
from src.experiments.cli import _check_dataset
from src.experiments.exp2_arms import arm_spec, n_expected
from src.experiments.exp2_config import Exp2Config
from src.experiments.exp2_pilot import pilot_check
from src.experiments.exp2_pipeline import Exp2Fit, fit_exp2_arm, score_exp2
from src.experiments.exp2_report import LLM_ARMS, build_report, render_markdown
from src.experiments.pipeline import write_decisions
from src.experiments.runner import ArmLike, run_arm
from src.experiments.verdict import DatasetVerdict, combine
from src.judges.jev_executor import JevStageExecutor
from src.storage import db
from src.storage.reader import completed_units, load_experiment_config
from src.storage.writer import SqliteStorageWriter


def load_config(path: str) -> Exp2Config:
    """Parse an Experiment 2 JSON config file."""
    return Exp2Config.model_validate_json(Path(path).read_text())


def _spec(cfg: Exp2Config, arm: str, study_id: str | None = None) -> ArmLike:
    return arm_spec(study_id or cfg.study_id, arm, cfg.n_replicas, cfg.data.horizon)


async def _run(args: argparse.Namespace) -> None:
    """Run one arm over one split against the real Jev API (human-only)."""
    Settings.load()  # fail fast if the credential is missing; value unused
    cfg = load_config(args.config)
    source = load_source(cfg.data)
    spec = _spec(cfg, args.arm, args.study_id)
    Path(cfg.db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(cfg.db_path)
    writer = SqliteStorageWriter(conn)
    extra = {
        "data": cfg.data.model_dump(),
        "dataset_id": dataset_identity(cfg.data),
        "excluded": source.excluded,
        "requested_model": cfg.model,
        "extra_body": cfg.extra_body,
        "pricing": cfg.pricing.model_dump() if cfg.pricing else None,
    }
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


def _pilot_check(args: argparse.Namespace) -> None:
    """Print the §9 stop-rule outcome for the stored arms; exit 1 on stop."""
    cfg = load_config(args.config)
    source = load_source(cfg.data)
    conn = db.connect(cfg.db_path)
    experiments = {}
    for arm in LLM_ARMS:
        eid = _spec(cfg, arm).experiment_id
        if load_experiment_config(conn, eid) is not None:  # only arms that ran
            experiments[eid] = n_expected(arm, cfg.n_replicas)
    check = pilot_check(conn, experiments, source.samples("pilot"), cfg)
    print(json.dumps(check.model_dump(), indent=2))
    if check.stop:
        sys.exit(1)


def _check_complete(
    conn: sqlite3.Connection, source: DataSource, spec: ArmLike
) -> None:
    """Refuse to fit before every calib/thresh unit has a recorded call.

    Freezing is irreversible, so fitting on a half-finished run would lock
    in a calibrator and margins that finishing the run could never repair.
    """
    done = completed_units(conn, spec.experiment_id)
    stages = [stage for stage, _ in spec.units()]
    missing = sum(
        (s.input_id, stage) not in done
        for split in ("calib", "thresh")
        for s in source.samples(split)
        for stage in stages
    )
    if missing:
        raise ValueError(
            f"{spec.experiment_id!r} is incomplete: {missing} calib/thresh units "
            "have no recorded call; run them first (or pass --allow-incomplete)"
        )


async def _fit(args: argparse.Namespace) -> None:
    """Freeze the Platt fit and margins (or reuse them) and write decisions."""
    cfg = load_config(args.config)
    source = load_source(cfg.data)
    conn = db.connect(cfg.db_path)
    writer = SqliteStorageWriter(conn)
    spec = _spec(cfg, args.arm)
    eid = spec.experiment_id
    stored = load_experiment_config(conn, eid)
    if stored is None:
        raise ValueError(f"unknown experiment {eid!r}; run the arm first")
    _check_dataset(conn, cfg, eid)
    frozen = stored.get("frozen", {})
    if "fit" in frozen:  # re-run after an interruption: reuse the frozen fit
        fit = Exp2Fit.model_validate(frozen["fit"])
    else:
        if not args.allow_incomplete:
            _check_complete(conn, source, spec)
        fit = await fit_exp2_arm(
            conn,
            writer,
            eid,
            n_expected(args.arm, cfg.n_replicas),
            source.samples("calib"),
            source.samples("thresh"),
            cfg,
            allow_degenerate=args.allow_degenerate,
        )
    rows = score_exp2(conn, fit, source.samples(args.decisions_split))
    headline = fit.margins[cfg.target_key(cfg.headline_coverage)].margin
    await write_decisions(conn, writer, fit, rows, headline)
    print(f"{eid}: fit frozen, decisions written for {args.decisions_split}")


def load_report(
    config_path: str, split: str, arms: list[str], preliminary: bool
) -> dict[str, Any]:
    """Build the report for one config after checking each arm's dataset."""
    cfg = load_config(config_path)
    source = load_source(cfg.data)
    conn = db.connect(cfg.db_path)
    for arm in arms:
        _check_dataset(conn, cfg, _spec(cfg, arm).experiment_id)
    return build_report(conn, cfg, source, split, arms, preliminary=preliminary)


def _report(args: argparse.Namespace) -> None:
    """Print the markdown report for one split."""
    report = load_report(args.config, args.split, args.arms, args.preliminary)
    print(render_markdown(report))


def _dataset_lines(name: str, verdict: DatasetVerdict) -> list[str]:
    outcome = "passes" if verdict.passed else "fails"
    lines = [f"{name}: {outcome} (attributable: {verdict.attributable})"]
    lines += [
        f"  - {k}: {'met' if v else 'not met'}" for k, v in verdict.criteria.items()
    ]
    lines += [f"  - note: {n}" for n in verdict.notes]
    return lines


def _verdict(args: argparse.Namespace) -> None:
    """Combine the ECB (primary) and synthetic `test` verdicts (§11)."""
    verdicts = {}
    for name, path in (("ECB", args.ecb_config), ("synthetic", args.synthetic_config)):
        report = load_report(path, "test", list(LLM_ARMS), preliminary=False)
        verdicts[name] = DatasetVerdict.model_validate(report["verdict"])
    label, wording = combine(verdicts["ECB"], verdicts["synthetic"])
    lines = [f"Verdict: {label}", wording, ""]
    lines += _dataset_lines("ECB (primary)", verdicts["ECB"])
    lines += _dataset_lines("synthetic", verdicts["synthetic"])
    print("\n".join(lines))


def main(argv: list[str] | None = None) -> None:
    """Parse `argv` and dispatch to one Experiment 2 subcommand."""
    parser = argparse.ArgumentParser(prog="exp2")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one arm over one split (spends API budget)")
    run.add_argument("--config", required=True)
    run.add_argument("--arm", choices=list(LLM_ARMS), required=True)
    run.add_argument("--split", choices=list(SPLITS), required=True)
    run.add_argument("--max-units", type=int, default=None)
    run.add_argument(
        "--study-id",
        default=None,
        help="override config study_id (fit/report always use the config's)",
    )

    pc = sub.add_parser("pilot-check", help="§9 stop rules on the pilot split")
    pc.add_argument("--config", required=True)

    fit = sub.add_parser("fit", help="freeze Platt fit + margins, write decisions")
    fit.add_argument("--config", required=True)
    fit.add_argument("--arm", choices=list(LLM_ARMS), required=True)
    fit.add_argument(
        "--decisions-split", choices=["test", "test_shift"], default="test"
    )
    fit.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="freeze even if calib/thresh units are missing (irreversible)",
    )
    fit.add_argument(
        "--allow-degenerate",
        action="store_true",
        help="freeze even if calib/thresh had no valid sample (irreversible)",
    )

    rep = sub.add_parser("report", help="Experiment 2 report for one split")
    rep.add_argument("--config", required=True)
    rep.add_argument("--split", choices=["test", "test_shift"], default="test")
    rep.add_argument("--arms", nargs="+", choices=list(LLM_ARMS), default=None)
    rep.add_argument(
        "--preliminary",
        action="store_true",
        help="allow A'x5 to be absent on test (no attribution, verdict not final)",
    )

    ver = sub.add_parser("verdict", help="combine ECB and synthetic verdicts (§11)")
    ver.add_argument("--ecb-config", required=True)
    ver.add_argument("--synthetic-config", required=True)

    args = parser.parse_args(argv)
    if args.command == "run":
        asyncio.run(_run(args))
    elif args.command == "pilot-check":
        _pilot_check(args)
    elif args.command == "fit":
        asyncio.run(_fit(args))
    elif args.command == "report":
        if args.arms is None:
            args.arms = list(LLM_ARMS)
        _report(args)
    elif args.command == "verdict":
        _verdict(args)


if __name__ == "__main__":
    main()
