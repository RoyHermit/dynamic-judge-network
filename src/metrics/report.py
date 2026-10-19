"""Arm summaries and the A-vs-C comparison (spec §6.6, §7)."""

from __future__ import annotations

import json
from typing import Any

from src.aggregation.core import margin_grid
from src.experiments.config import Exp1Config, Pricing
from src.experiments.pipeline import ArmFit
from src.metrics.bootstrap import paired_block_ci
from src.metrics.core import (
    Row,
    accuracy_at_coverage,
    acted_accuracy_coverage,
    brier,
    log_loss,
    percentile,
    reliability,
    risk_coverage,
)
from src.storage.reader import CallRow, completion_latency


def arm_cost(calls: list[CallRow], pricing: Pricing | None) -> dict[str, Any]:
    """Token totals and cost; cost is None (never estimated) without pricing."""
    tokens_in = tokens_out = missing = 0
    for call in calls:
        usage = call.token_usage
        if not usage or "input_tokens" not in usage:
            missing += 1
            continue
        tokens_in += usage["input_tokens"]
        tokens_out += usage.get("output_tokens", 0)
    cost = None
    if pricing is not None:
        cost = (
            tokens_in * pricing.input_per_mtok + tokens_out * pricing.output_per_mtok
        ) / 1_000_000
    return {
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "calls_without_usage": missing,
        "cost_usd": cost,
    }


def _acc_cov(rows: list[Row], margin: float) -> dict[str, Any]:
    r = acted_accuracy_coverage(rows, margin)
    return {
        "accuracy": r.accuracy,
        "coverage_valid": r.coverage_valid,
        "coverage_all": r.coverage_all,
        "n_acted": r.n_acted,
    }


def _arm_summary(
    rows: list[Row], fit: ArmFit, cfg: Exp1Config, calls: list[CallRow]
) -> dict[str, Any]:
    targets = {
        key: {
            "margin": c.margin,
            "reached_target": c.reached,
            **_acc_cov(rows, c.margin),
        }
        for key, c in fit.margins.items()
    }
    headline = fit.margins[cfg.target_key(cfg.headline_coverage)].margin
    latencies = list(completion_latency(calls).values())
    n_valid = sum(r.p is not None for r in rows)
    return {
        "n_rows": len(rows),
        "n_valid": n_valid,
        "invalid_rate": (len(rows) - n_valid) / len(rows) if rows else 0.0,
        "targets": targets,
        "brier": brier(rows),
        "log_loss": log_loss(rows, cfg.logloss_delta),
        "reliability": reliability(rows),
        "by_regime_headline": {
            regime: _acc_cov([r for r in rows if r.regime == regime], headline)
            for regime in sorted({r.regime for r in rows})
        },
        "latency_p50": percentile(latencies, 0.5) if latencies else None,
        "latency_p95": percentile(latencies, 0.95) if latencies else None,
        "cost": arm_cost(calls, cfg.pricing),
    }


def _common_summary(
    common_a: list[Row],
    common_c: list[Row],
    fit_a: ArmFit,
    fit_c: ArmFit,
    cfg: Exp1Config,
) -> dict[str, Any]:
    grid = margin_grid(cfg.margin_step)
    curve_a, curve_c = risk_coverage(common_a, grid), risk_coverage(common_c, grid)
    targets: dict[str, Any] = {}
    for target in cfg.coverage_targets:
        key = cfg.target_key(target)
        ma, mc = fit_a.margins[key].margin, fit_c.margins[key].margin

        def stat(idx: list[int], ma: float = ma, mc: float = mc) -> float | None:
            a = acted_accuracy_coverage([common_a[i] for i in idx], ma).accuracy
            c = acted_accuracy_coverage([common_c[i] for i in idx], mc).accuracy
            return None if a is None or c is None else c - a

        targets[key] = {
            "A": _acc_cov(common_a, ma),
            "C": _acc_cov(common_c, mc),
            "matched_accuracy_A": accuracy_at_coverage(curve_a, target),
            "matched_accuracy_C": accuracy_at_coverage(curve_c, target),
            "diff_ci": paired_block_ci(
                len(common_a),
                cfg.bootstrap_block_len,
                cfg.bootstrap_resamples,
                cfg.bootstrap_seed,
                stat,
            ),
        }
    return {"targets": targets}


def compare_arms(
    rows_a: list[Row],
    rows_c: list[Row],
    fit_a: ArmFit,
    fit_c: ArmFit,
    cfg: Exp1Config,
    *,
    calls_a: list[CallRow],
    calls_c: list[CallRow],
    references: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Headline comparison on the common valid set; per-arm results alongside."""
    by_a = {r.input_id: r for r in rows_a}
    by_c = {r.input_id: r for r in rows_c}
    common_ids = sorted(
        (
            i
            for i, r in by_a.items()
            if r.p is not None and i in by_c and by_c[i].p is not None
        ),
        key=lambda i: by_a[i].t_index,
    )
    report: dict[str, Any] = {
        "n_labelled": len(rows_a),
        "n_common_valid": len(common_ids),
        "arms": {
            "A": _arm_summary(rows_a, fit_a, cfg, calls_a),
            "C": _arm_summary(rows_c, fit_c, cfg, calls_c),
        },
        "common": _common_summary(
            [by_a[i] for i in common_ids],
            [by_c[i] for i in common_ids],
            fit_a,
            fit_c,
            cfg,
        ),
        "references": references or {},
        "warnings": [],
    }
    for name, summary in report["arms"].items():
        if summary["invalid_rate"] > cfg.invalid_warn_rate:
            report["warnings"].append(
                f"arm {name}: invalid rate {summary['invalid_rate']:.1%} exceeds "
                f"{cfg.invalid_warn_rate:.1%}"
            )
    return report


def render_markdown(report: dict[str, Any]) -> str:
    """Compact text report: warnings first, then the common-set table."""
    lines = ["# Experiment 1 report", ""]
    for warning in report["warnings"]:
        lines.append(f"> WARNING: {warning}")
    lines += [
        f"labelled: {report['n_labelled']}, common valid: {report['n_common_valid']}",
        "",
        "| target | A acc | A cov | C acc | C cov | C-A 95% CI |",
        "|---|---|---|---|---|---|",
    ]
    for key, row in report["common"]["targets"].items():
        a, c = row["A"], row["C"]
        lines.append(
            f"| {key} | {a['accuracy']} | {a['coverage_valid']} | "
            f"{c['accuracy']} | {c['coverage_valid']} | {row['diff_ci']} |"
        )
    lines += ["", "```json", json.dumps(report["references"], indent=2), "```"]
    return "\n".join(lines)
