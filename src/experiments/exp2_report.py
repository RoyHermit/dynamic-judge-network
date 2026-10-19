"""Experiment 2 report (spec §3, §5, §6, §8, §11). Offline: reads the DB only.

Scores every arm with its frozen fit, adds the deterministic competitors,
runs the paired full-coverage comparisons on the §5 eligibility set and,
on `test`, applies the preregistered success rule.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Literal

from src.aggregation.core import margin_grid
from src.data.competitors import competitor_rows, fit_competitors
from src.data.ecb import EcbCsvConfig
from src.data.schema import DataSource, Sample
from src.data.synthetic import SyntheticConfig
from src.experiments.exp2_arms import arm_spec
from src.experiments.exp2_config import Exp2Config
from src.experiments.exp2_pipeline import (
    Exp2Fit,
    fit_unfrozen,
    score_exp2,
    subset_means,
)
from src.experiments.exp2_report_sections import (
    ROLE_JUDGES,
    diagnostics_section,
    render_diagnostics,
)
from src.experiments.exp2_report_sections import fmt_cell as _fmt
from src.experiments.verdict import evaluate_dataset
from src.metrics.core import (
    Row,
    accuracy_at_coverage,
    brier,
    log_loss,
    percentile,
    reliability,
    risk_coverage,
)
from src.metrics.paired import (
    PairedDiff,
    eligible_ids,
    full_coverage_correct,
    paired_accuracy_diff,
)
from src.metrics.report import _acc_cov, arm_cost
from src.storage.reader import completion_latency, load_calls, load_experiment_config

ECB_NOTE = "ECB result is exploratory with respect to prior knowledge"
CI_NOTE = (
    "bootstrap intervals condition on the frozen calibrator and margins "
    "and omit fitting uncertainty"
)
SECONDARY_NOTE = (
    "test_shift is a secondary generalisation check: not part of the success rule"
)
PRELIMINARY_NOTE = (
    "preliminary: the eligibility set excludes A'x5 (not yet run), so "
    "attribution is unavailable and the verdict is not final"
)

NO_VOL_NOTE = (
    "D-noVol is recomputed from D's stored answers (no extra calls); "
    "its cost and latency are not reported"
)

LLM_ARMS: tuple[str, ...] = ("A", "C", "Ap", "Ap5", "D")
RULE_LLM_ARMS: tuple[str, ...] = ("D", "Ap", "Ap5")  # §5 eligibility arms
SECONDARY_ARMS: tuple[str, ...] = ("D", "Ap", "L", "M", "Majority")
# comparison key -> (x, y); the reported difference is accuracy(x) - accuracy(y)
COMPARISONS: dict[str, tuple[str, str]] = {
    "D-Ap": ("D", "Ap"),
    "D-Majority": ("D", "Majority"),
    "D-L": ("D", "L"),
    "D-M": ("D", "M"),
    "D-Ap5": ("D", "Ap5"),
    "D-A": ("D", "A"),
    "D-C": ("D", "C"),
    "D-Const": ("D", "Const"),
    "D-noVol vs D": ("D-noVol", "D"),
}
SECONDARY_COMPARISONS: tuple[str, ...] = ("D-Ap", "D-Majority", "D-L", "D-M")
NO_VOL_EXCLUDE = frozenset({"role_volatility"})


def load_frozen_fit(conn: sqlite3.Connection, experiment_id: str) -> Exp2Fit:
    """The fit frozen under `config_json["frozen"]["fit"]`; ValueError if absent."""
    config = load_experiment_config(conn, experiment_id)
    if config is None:
        raise ValueError(f"no experiment {experiment_id!r} in the database")
    fit = config.get("frozen", {}).get("fit")
    if fit is None:
        raise ValueError(f"no frozen fit for {experiment_id!r}; run the fit step first")
    return Exp2Fit.model_validate(fit)


def report_notes(
    data: SyntheticConfig | EcbCsvConfig,
    *,
    secondary: bool = False,
    preliminary: bool = False,
) -> list[str]:
    """Standing notes: ECB exploratory label, CI assumption, scope labels."""
    notes = [ECB_NOTE] if isinstance(data, EcbCsvConfig) else []
    notes.append(CI_NOTE)
    if secondary:
        notes.append(SECONDARY_NOTE)
    if preliminary:
        notes.append(PRELIMINARY_NOTE)
    return notes


def _full_accuracy(rows: list[Row]) -> float | None:
    """Full-coverage accuracy over the arm's own valid rows."""
    valid = [r for r in rows if r.p is not None]
    return sum(map(full_coverage_correct, valid)) / len(valid) if valid else None


def _probability_summary(rows: list[Row], cfg: Exp2Config) -> dict[str, Any]:
    """Metrics shared by every arm (LLM or deterministic)."""
    n_valid = sum(r.p is not None for r in rows)
    curve = risk_coverage(rows, margin_grid(cfg.margin_step))
    return {
        "n_rows": len(rows),
        "n_valid": n_valid,
        "invalid_rate": (len(rows) - n_valid) / len(rows) if rows else 0.0,
        # full coverage: invalid samples count as not acted
        "coverage_all": n_valid / len(rows) if rows else 0.0,
        "accuracy_full": _full_accuracy(rows),
        "matched_accuracy": accuracy_at_coverage(curve, cfg.headline_coverage),
        "brier": brier(rows),
        "log_loss": log_loss(rows, cfg.logloss_delta),
        "reliability": reliability(rows),
    }


def _raw_rows(
    conn: sqlite3.Connection, fit: Exp2Fit, samples: list[Sample]
) -> list[Row]:
    """Rows whose p is the uncalibrated mean probability."""
    means = subset_means(
        conn, fit.experiment_id, fit.n_expected, samples, frozenset(fit.exclude_judges)
    )
    return [
        Row(
            input_id=s.input_id,
            regime=s.regime,
            label=s.label,
            t_index=s.t_index,
            p=means[s.input_id],
        )
        for s in samples
    ]


def _cost_latency(
    conn: sqlite3.Connection, experiment_id: str, rows: list[Row], cfg: Exp2Config
) -> dict[str, Any]:
    """Tokens, cost and completion latency over the evaluated inputs only."""
    evaluated = {r.input_id for r in rows}
    calls = [c for c in load_calls(conn, experiment_id) if c.input_id in evaluated]
    latencies = list(completion_latency(calls).values())
    return {
        "latency_p50": percentile(latencies, 0.5) if latencies else None,
        "latency_p95": percentile(latencies, 0.95) if latencies else None,
        "cost": arm_cost(calls, cfg.pricing, len(rows)),
    }


def _llm_arm(
    conn: sqlite3.Connection,
    fit: Exp2Fit,
    samples: list[Sample],
    cfg: Exp2Config,
    *,
    own_calls: bool = True,
) -> tuple[list[Row], dict[str, Any]]:
    """Platt rows and the full per-arm summary of one scored LLM arm.

    `own_calls=False` (D-noVol, recomputed from D's stored answers) reports
    no cost or latency instead of duplicating D's.
    """
    rows = score_exp2(conn, fit, samples)
    iso = score_exp2(conn, fit, samples, calibrator="isotonic")
    raw = _raw_rows(conn, fit, samples)
    summary = {
        "experiment_id": fit.experiment_id,
        **_probability_summary(rows, cfg),
        "brier_raw": brier(raw),
        "log_loss_raw": log_loss(raw, cfg.logloss_delta),
        "isotonic": {
            "accuracy_full": _full_accuracy(iso),
            "brier": brier(iso),
            "log_loss": log_loss(iso, cfg.logloss_delta),
        },
        "targets": {
            key: {
                "margin": c.margin,
                "reached_target": c.reached,
                **_acc_cov(rows, c.margin),
            }
            for key, c in fit.margins.items()
        },
        "platt_fallback": fit.platt.fallback,
        "degenerate": fit.degenerate,
        **(
            _cost_latency(conn, fit.experiment_id, rows, cfg)
            if own_calls
            else {"latency_p50": None, "latency_p95": None, "cost": None}
        ),
    }
    return rows, summary


def select_arms(
    split: str, arms: list[str], preliminary: bool
) -> tuple[list[str], list[str]]:
    """(LLM arms to score, eligibility arms); ValueError on a missing arm."""
    unknown = sorted(set(arms) - set(LLM_ARMS))
    if unknown:
        raise ValueError(f"unknown arms: {unknown}")
    for needed in ("D", "Ap"):
        if needed not in arms:
            raise ValueError(f"arm {needed!r} is required for the report")
    if split == "test_shift":
        scored = [a for a in LLM_ARMS if a in arms and a in SECONDARY_ARMS]
        return scored, [a for a in RULE_LLM_ARMS if a in scored]
    if "Ap5" not in arms and not preliminary:
        raise ValueError(
            "arm 'Ap5' is missing: the §5 eligibility set needs it; "
            "pass preliminary=True for a preliminary report"
        )
    scored = [a for a in LLM_ARMS if a in arms]
    return scored, [a for a in RULE_LLM_ARMS if a in scored]


def _compare(
    rows_by_arm: dict[str, list[Row]],
    eligible: list[str],
    keys: tuple[str, ...] | list[str],
    cfg: Exp2Config,
) -> dict[str, dict[str, Any] | None]:
    """Paired diffs on the eligibility set; None when an arm is absent.

    Arms outside the eligibility set (A, C, D-noVol) are compared on the
    eligible ids where they are also valid; `n` records the size used.
    """
    out: dict[str, dict[str, Any] | None] = {}
    for key in keys:
        x, y = COMPARISONS[key]
        if x not in rows_by_arm or y not in rows_by_arm:
            out[key] = None
            continue
        valid = {r.input_id for r in rows_by_arm[x] if r.p is not None} & {
            r.input_id for r in rows_by_arm[y] if r.p is not None
        }
        ids = [i for i in eligible if i in valid]
        out[key] = paired_accuracy_diff(
            rows_by_arm[x], rows_by_arm[y], ids, cfg
        ).model_dump()
    return out


def _verdict(
    comparisons: dict[str, dict[str, Any] | None], cfg: Exp2Config
) -> dict[str, Any]:
    """§5 success rule on this dataset; attribution None without A'x5."""

    def get(key: str) -> PairedDiff:
        value = comparisons.get(key)
        if value is None:
            raise ValueError(f"comparison {key!r} is required for the verdict")
        return PairedDiff.model_validate(value)

    ap5 = comparisons.get("D-Ap5")
    return evaluate_dataset(
        get("D-Ap"),
        get("D-Majority"),
        get("D-L"),
        get("D-M"),
        None if ap5 is None else PairedDiff.model_validate(ap5),
        cfg.min_gain,
    ).model_dump()


def _arm_warnings(arms: dict[str, dict[str, Any]], cfg: Exp2Config) -> list[str]:
    """Invalid-rate, Platt-fallback and degenerate-fit notes per arm."""
    notes = []
    for name, s in arms.items():
        if s["invalid_rate"] > cfg.invalid_warn_rate:
            notes.append(
                f"arm {name}: invalid rate {s['invalid_rate']:.1%} exceeds "
                f"{cfg.invalid_warn_rate:.1%}"
            )
        if s.get("platt_fallback"):
            notes.append(f"arm {name}: Platt fell back ({s['platt_fallback']})")
        if s.get("degenerate"):
            notes.append(f"arm {name}: degenerate fit, every row is invalid")
    return notes


def build_report(
    conn: sqlite3.Connection,
    cfg: Exp2Config,
    source: DataSource,
    split: Literal["test", "test_shift"],
    arms: list[str],
    *,
    preliminary: bool = False,
) -> dict[str, Any]:
    """JSON-serialisable Experiment 2 report for one dataset and split.

    `arms` lists the LLM arms that were run and fitted. On `test`, A'x5 is
    required unless `preliminary`; `test_shift` is secondary (D, A', L, M,
    Majority only, no verdict).
    """
    secondary = split == "test_shift"
    scored, rule_arms = select_arms(split, arms, preliminary)
    # flag, note, heading and eligibility set must agree: preliminary only
    # means "test without A'x5"
    preliminary = preliminary and "Ap5" not in scored and split == "test"
    dropped = [a for a in arms if a not in scored]
    calib, thresh = source.samples("calib"), source.samples("thresh")
    samples = source.samples(split)
    horizon = cfg.data.horizon
    ids = {
        a: arm_spec(cfg.study_id, a, cfg.n_replicas, horizon).experiment_id
        for a in scored
    }
    rows_by_arm: dict[str, list[Row]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    for arm in scored:
        rows_by_arm[arm], summaries[arm] = _llm_arm(
            conn, load_frozen_fit(conn, ids[arm]), samples, cfg
        )
    if not secondary:
        no_vol = fit_unfrozen(
            conn, ids["D"], len(ROLE_JUDGES) - 1, calib, thresh, cfg, NO_VOL_EXCLUDE
        )  # prespecified ablation: recomputed from D's answers, never frozen
        rows_by_arm["D-noVol"], summaries["D-noVol"] = _llm_arm(
            conn, no_vol, samples, cfg, own_calls=False
        )
    for name, rows in competitor_rows(fit_competitors(calib, thresh), samples).items():
        if not secondary or name in SECONDARY_ARMS:
            rows_by_arm[name] = rows
            summaries[name] = _probability_summary(rows, cfg)
    eligible = eligible_ids(rows_by_arm, rule_arms)
    comparisons = _compare(
        rows_by_arm,
        eligible,
        SECONDARY_COMPARISONS if secondary else tuple(COMPARISONS),
        cfg,
    )
    notes = report_notes(cfg.data, secondary=secondary, preliminary=preliminary)
    if not secondary:
        notes.append(NO_VOL_NOTE)
    if dropped:
        notes.append(f"arms not reported on {split}: {', '.join(dropped)}")
    return {
        "study_id": cfg.study_id,
        "dataset": cfg.data.source,
        "split": split,
        "secondary": secondary,
        "preliminary": preliminary,
        "n_labelled": len(samples),
        "eligibility": {"llm_arms": rule_arms, "n": len(eligible)},
        "arms": summaries,
        "comparisons": comparisons,
        "diagnostics": (
            None
            if secondary
            else diagnostics_section(conn, cfg, ids, calib, thresh, samples, eligible)
        ),
        "verdict": None if secondary else _verdict(comparisons, cfg),
        "notes": notes + _arm_warnings(summaries, cfg),
    }


def _arms_table(arms: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "## Arms",
        "",
        (
            "| arm | valid/n | invalid | cov (all) | acc (full) | matched acc | "
            "brier | log loss | brier raw | log loss raw | iso acc | "
            "latency p50 | cost USD |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, a in arms.items():
        iso = a.get("isotonic", {})
        cost = a.get("cost") or {}
        lines.append(
            f"| {name} | {a['n_valid']}/{a['n_rows']} | {_fmt(a['invalid_rate'])} | "
            f"{_fmt(a['coverage_all'])} | {_fmt(a['accuracy_full'])} | "
            f"{_fmt(a['matched_accuracy'])} | {_fmt(a['brier'])} | "
            f"{_fmt(a['log_loss'])} | {_fmt(a.get('brier_raw'))} | "
            f"{_fmt(a.get('log_loss_raw'))} | {_fmt(iso.get('accuracy_full'))} | "
            f"{_fmt(a.get('latency_p50'))} | {_fmt(cost.get('cost_usd'))} |"
        )
    return lines


def _comparisons_table(report: dict[str, Any]) -> list[str]:
    elig = report["eligibility"]
    lines = [
        "## Comparisons (full-coverage accuracy, x - y)",
        "",
        f"eligibility set: valid in {', '.join(elig['llm_arms'])} (n = {elig['n']})",
        "",
        "| comparison | n | acc x | acc y | diff | 95% CI |",
        "|---|---|---|---|---|---|",
    ]
    for key, c in report["comparisons"].items():
        if c is None:
            lines.append(f"| {key} | arm not run | | | | |")
            continue
        lines.append(
            f"| {key} | {c['n']} | {_fmt(c['acc_x'])} | {_fmt(c['acc_y'])} | "
            f"{_fmt(c['diff'])} | {_fmt(c['ci'])} |"
        )
    return lines


def _verdict_lines(verdict: dict[str, Any]) -> list[str]:
    lines = ["## Verdict (§5 success rule)", "", f"passed: {verdict['passed']}", ""]
    lines += [f"- {name}: {ok}" for name, ok in verdict["criteria"].items()]
    lines.append(
        f"- attributable to decomposition (D > A'x5): {verdict['attributable']}"
    )
    lines += [f"- {n}" for n in verdict["notes"]]
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    """Human-readable report: notes, arms, comparisons, diagnostics, verdict."""
    label = " (secondary)" if report["secondary"] else ""
    if report["preliminary"]:
        label += " (preliminary)"
    lines = [
        f"# Experiment 2 report: {report['study_id']} / {report['split']}{label}",
        "",
        f"dataset: {report['dataset']}, labelled: {report['n_labelled']}",
        "",
        "## Notes",
        "",
        *[f"- {n}" for n in report["notes"]],
        "",
        *_arms_table(report["arms"]),
        "",
        *_comparisons_table(report),
    ]
    if report["diagnostics"] is not None:
        lines += ["", *render_diagnostics(report["diagnostics"])]
    if report["verdict"] is not None:
        lines += ["", *_verdict_lines(report["verdict"])]
    return "\n".join(lines) + "\n"
