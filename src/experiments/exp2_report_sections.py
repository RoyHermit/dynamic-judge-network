"""Diagnostics section of the Experiment 2 report (spec §6). Offline, no API.

Every Judge is calibrated on `calib` only; correlations that are undefined
(constant vectors, fewer than two aligned samples, or a Judge whose calibrated
call is constant: `constant_prediction`) stay None, never 0.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from src.data.schema import Sample
from src.experiments.exp2_config import Exp2Config
from src.features.indicators import ROLES
from src.metrics.core import Row
from src.metrics.diagnostics import (
    aligned_error_vectors,
    constant_prediction_judges,
    fit_judge_platt,
    full_set_accuracy,
    judge_diagnostics,
    judge_rows,
    leave_one_out,
    masked_pairwise_correlations,
    mean_defined,
    pairwise_disagreement,
    residual_vectors,
)

ROLE_JUDGES: tuple[str, ...] = tuple(f"role_{r}" for r in ROLES)


def ap5_judges(n_replicas: int) -> list[str]:
    """Judge ids of the A'x5 replicas."""
    return [f"ap_judge#{k}" for k in range(n_replicas)]


def _pair_key(a: str, b: str) -> str:
    """JSON-safe key of a judge pair."""
    return f"{a}|{b}"


def judge_section(
    conn: sqlite3.Connection,
    experiment_id: str,
    judges: list[str],
    calib: list[Sample],
    samples: list[Sample],
    cfg: Exp2Config,
) -> tuple[dict[str, list[Row]], dict[str, Any]]:
    """Per-Judge Platt (fitted on `calib`) rows and accuracy/Brier on `samples`."""
    rows_by_judge: dict[str, list[Row]] = {}
    summary: dict[str, Any] = {}
    for judge in judges:
        platt = fit_judge_platt(conn, experiment_id, calib, judge, cfg.platt_l2)
        rows = judge_rows(conn, experiment_id, samples, platt, judge)
        rows_by_judge[judge] = rows
        summary[judge] = {
            **judge_diagnostics(rows).model_dump(),
            "platt_fallback": platt.fallback,
        }
    return rows_by_judge, summary


def _pairwise(
    vectors: dict[str, list[float]], undefined: set[str]
) -> dict[str, float | None]:
    """JSON-keyed pairwise correlations; pairs with an `undefined` judge are None."""
    return {
        _pair_key(a, b): c
        for (a, b), c in masked_pairwise_correlations(vectors, undefined).items()
    }


def correlation_section(rows_by_judge: dict[str, list[Row]]) -> dict[str, Any]:
    """Error-vector (primary) and residual (secondary) correlations.

    Judges with a constant calibrated call over the aligned ids are listed
    under `constant_prediction`; every pair involving one is None (undefined)
    and is left out of the means (spec §6).
    """
    errors = aligned_error_vectors(rows_by_judge)
    residuals = residual_vectors(rows_by_judge)
    constant = constant_prediction_judges(rows_by_judge)
    pairwise_error = _pairwise(errors, set(constant))
    pairwise_residual = _pairwise(residuals, set(constant))
    return {
        "n_aligned": len(next(iter(errors.values()), [])),
        "constant_prediction": constant,
        "mean_error": mean_defined(list(pairwise_error.values())),
        "mean_residual": mean_defined(list(pairwise_residual.values())),
        "pairwise_error": pairwise_error,
        "pairwise_residual": pairwise_residual,
    }


def disagreement_section(rows_by_judge: dict[str, list[Row]]) -> dict[str, float]:
    """Pairwise share of differing calibrated calls, keyed `a|b`."""
    return {
        _pair_key(a, b): v for (a, b), v in pairwise_disagreement(rows_by_judge).items()
    }


def leave_one_out_section(
    conn: sqlite3.Connection,
    d_experiment_id: str,
    calib: list[Sample],
    thresh: list[Sample],
    samples: list[Sample],
    cfg: Exp2Config,
    ids: list[str],
) -> dict[str, Any]:
    """D's full-coverage accuracy on `ids` with all roles and each role dropped."""
    roles = list(ROLE_JUDGES)
    return {
        "full": full_set_accuracy(
            conn, d_experiment_id, len(roles), calib, thresh, samples, cfg, ids
        ),
        "without": leave_one_out(
            conn, d_experiment_id, roles, calib, thresh, samples, cfg, ids
        ),
    }


def diagnostics_section(
    conn: sqlite3.Connection,
    cfg: Exp2Config,
    experiment_ids: dict[str, str],
    calib: list[Sample],
    thresh: list[Sample],
    samples: list[Sample],
    ids: list[str],
) -> dict[str, Any]:
    """All §6 diagnostics; A'x5 entries are None when that arm is absent."""
    groups: dict[str, list[str]] = {"D": list(ROLE_JUDGES)}
    if "Ap5" in experiment_ids:
        groups["Ap5"] = ap5_judges(cfg.n_replicas)
    judges: dict[str, Any] = {}
    correlation: dict[str, Any] = {"D": None, "Ap5": None}
    disagreement: dict[str, Any] = {"D": None, "Ap5": None}
    for arm, judge_ids in groups.items():
        rows, summary = judge_section(
            conn, experiment_ids[arm], judge_ids, calib, samples, cfg
        )
        correlation[arm] = correlation_section(rows)
        for judge in summary:
            summary[judge]["constant_prediction"] = (
                judge in correlation[arm]["constant_prediction"]
            )
        judges.update(summary)
        disagreement[arm] = disagreement_section(rows)
    loo = leave_one_out_section(
        conn, experiment_ids["D"], calib, thresh, samples, cfg, ids
    )
    return {
        "judges": judges,
        "correlation": correlation,
        "disagreement": disagreement,
        "leave_one_out": loo["without"],
        "leave_one_out_full": loo["full"],
    }


def fmt_cell(value: Any) -> str:
    """Compact markdown cell text; None prints as `n/a`."""
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(fmt_cell(v) for v in value) + "]"
    return str(value)


def render_diagnostics(diag: dict[str, Any]) -> list[str]:
    """Markdown lines for the diagnostics section of the report."""
    lines = [
        "## Diagnostics (not success criteria)",
        "",
        "| judge | accuracy | brier | Platt fallback |",
        "|---|---|---|---|",
    ]
    for judge, d in diag["judges"].items():
        lines.append(
            f"| {judge} | {fmt_cell(d['accuracy'])} | {fmt_cell(d['brier'])} | "
            f"{fmt_cell(d['platt_fallback'])} |"
        )
    lines += ["", "mean pairwise correlation (undefined = n/a, never 0):"]
    for arm, c in diag["correlation"].items():
        if c is None:
            lines.append(f"- {arm}: arm not run")
            continue
        lines.append(
            f"- {arm}: error {fmt_cell(c['mean_error'])}, "
            f"residual {fmt_cell(c['mean_residual'])} (n = {c['n_aligned']})"
        )
        if c["constant_prediction"]:
            lines.append(
                f"- {arm}: constant_prediction (calibrated call never changes; "
                f"its correlations are undefined): {', '.join(c['constant_prediction'])}"
            )
    for arm, d in diag["disagreement"].items():
        if d:
            pairs = ", ".join(f"{k} {fmt_cell(v)}" for k, v in d.items())
            lines.append(f"- disagreement {arm}: {pairs}")
    lines += [
        "",
        (
            "leave-one-out (D accuracy with all roles: "
            f"{fmt_cell(diag['leave_one_out_full'])}):"
        ),
    ]
    lines += [f"- without {r}: {fmt_cell(v)}" for r, v in diag["leave_one_out"].items()]
    return lines
