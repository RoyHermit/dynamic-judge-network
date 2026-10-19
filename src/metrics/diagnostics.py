"""Per-judge diagnostics for Experiment 2 (spec §6): calibration, error
correlation, disagreement, leave-one-out. Judge-level Platt fits use `calib` only."""

from __future__ import annotations

import itertools
import sqlite3
import statistics

from pydantic import BaseModel

from src.aggregation.platt import PlattCalibrator
from src.data.schema import Sample
from src.experiments.exp2_config import Exp2Config
from src.experiments.exp2_pipeline import fit_unfrozen, score_exp2
from src.metrics.core import Row, brier
from src.metrics.paired import full_coverage_correct
from src.storage.reader import load_probabilities


def fit_judge_platt(
    conn: sqlite3.Connection,
    experiment_id: str,
    calib: list[Sample],
    judge_id: str,
    l2: float,
) -> PlattCalibrator:
    """Fit a Platt calibrator on one judge's raw P(HIGH) over `calib` only.

    Calib samples without a valid answer from that judge are skipped.
    """
    probs = load_probabilities(conn, experiment_id)
    ps: list[float] = []
    ys: list[float] = []
    for s in calib:
        p = probs.get(s.input_id, {}).get(judge_id)
        if p is not None:
            ps.append(p)
            ys.append(1.0 if s.label == "HIGH" else 0.0)
    return PlattCalibrator.fit(ps, ys, l2)


def judge_rows(
    conn: sqlite3.Connection,
    experiment_id: str,
    samples: list[Sample],
    platt: PlattCalibrator,
    judge_id: str,
) -> list[Row]:
    """Calibrated rows of one judge; `p` is None where it has no valid answer."""
    probs = load_probabilities(conn, experiment_id)
    rows = []
    for s in samples:
        raw = probs.get(s.input_id, {}).get(judge_id)
        rows.append(
            Row(
                input_id=s.input_id,
                regime=s.regime,
                label=s.label,
                t_index=s.t_index,
                p=None if raw is None else platt.predict(raw),
            )
        )
    return rows


def error_vector(rows: list[Row]) -> list[int]:
    """1 where the calibrated call (p >= 0.5) is wrong, over rows with a p."""
    return [1 - full_coverage_correct(r) for r in rows if r.p is not None]


def _common_valid(rows_by_judge: dict[str, list[Row]]) -> dict[str, dict[str, Row]]:
    """Per judge, rows keyed by input_id restricted to ids valid for all judges."""
    by_judge = {
        j: {r.input_id: r for r in rows if r.p is not None}
        for j, rows in rows_by_judge.items()
    }
    if not by_judge:
        return {}
    common = set.intersection(*(set(m) for m in by_judge.values()))
    return {j: {i: m[i] for i in common} for j, m in by_judge.items()}


def _ordered_ids(common: dict[str, dict[str, Row]]) -> list[str]:
    """Common ids ordered by (t_index, id)."""
    first = next(iter(common.values()), {})
    return sorted(first, key=lambda i: (first[i].t_index, i))


def aligned_error_vectors(
    rows_by_judge: dict[str, list[Row]],
) -> dict[str, list[float]]:
    """Error vectors on the ids valid for every judge, ordered by t_index."""
    common = _common_valid(rows_by_judge)
    ids = _ordered_ids(common)
    return {
        j: [float(1 - full_coverage_correct(m[i])) for i in ids]
        for j, m in common.items()
    }


def residual_vectors(rows_by_judge: dict[str, list[Row]]) -> dict[str, list[float]]:
    """Calibrated residuals `p - label` (HIGH = 1) on the same aligned ids."""
    common = _common_valid(rows_by_judge)
    ids = _ordered_ids(common)
    return {
        j: [m[i].p - (1.0 if m[i].label == "HIGH" else 0.0) for i in ids]
        for j, m in common.items()
    }


def safe_correlation(a: list[float], b: list[float]) -> float | None:
    """Pearson correlation; None if undefined (constant series or length < 2)."""
    if len(a) != len(b):
        raise ValueError("series lengths differ")
    if len(a) < 2:
        return None
    try:
        return statistics.correlation(a, b)
    except statistics.StatisticsError:
        return None


def mean_pairwise_correlation(vectors: list[list[float]]) -> float | None:
    """Mean of the defined pairwise correlations; None if none is defined."""
    values = [
        c
        for x, y in itertools.combinations(vectors, 2)
        if (c := safe_correlation(x, y)) is not None
    ]
    return sum(values) / len(values) if values else None


def pairwise_disagreement(
    rows_by_judge: dict[str, list[Row]],
) -> dict[tuple[str, str], float]:
    """Share of commonly valid ids where two judges' calls (p >= 0.5) differ.

    Keyed by the sorted judge pair; pairs with no common id are omitted.
    """
    out: dict[tuple[str, str], float] = {}
    for a, b in itertools.combinations(sorted(rows_by_judge), 2):
        common = _common_valid({a: rows_by_judge[a], b: rows_by_judge[b]})
        ids = list(common[a])
        if not ids:
            continue
        diff = sum((common[a][i].p >= 0.5) != (common[b][i].p >= 0.5) for i in ids)
        out[(a, b)] = diff / len(ids)
    return out


class JudgeDiagnostics(BaseModel):
    """Calibrated accuracy (p >= 0.5) and Brier score of one judge."""

    accuracy: float | None
    brier: float | None


def judge_diagnostics(rows: list[Row]) -> JudgeDiagnostics:
    """Accuracy and Brier over the rows that have a calibrated p."""
    valid = [r for r in rows if r.p is not None]
    return JudgeDiagnostics(
        accuracy=(
            sum(full_coverage_correct(r) for r in valid) / len(valid) if valid else None
        ),
        brier=brier(rows),
    )


def _accuracy_on_ids(rows: list[Row], ids: list[str]) -> float | None:
    """Full-coverage accuracy on `ids`; ValueError if an id is missing/invalid."""
    if not ids:
        return None
    by_id = {r.input_id: r for r in rows}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise ValueError(f"ids missing from rows: {missing[:3]}")
    return sum(full_coverage_correct(by_id[i]) for i in ids) / len(ids)


def full_set_accuracy(
    conn: sqlite3.Connection,
    experiment_id: str,
    n_roles: int,
    calib: list[Sample],
    thresh: list[Sample],
    samples: list[Sample],
    cfg: Exp2Config,
    ids: list[str],
) -> float | None:
    """Full-coverage accuracy on `ids` with all `n_roles` judges (D), for comparison."""
    fit = fit_unfrozen(conn, experiment_id, n_roles, calib, thresh, cfg, frozenset())
    return _accuracy_on_ids(score_exp2(conn, fit, samples), ids)


def leave_one_out(
    conn: sqlite3.Connection,
    experiment_id: str,
    roles: list[str],
    calib: list[Sample],
    thresh: list[Sample],
    samples: list[Sample],
    cfg: Exp2Config,
    ids: list[str],
) -> dict[str, float | None]:
    """Full-coverage accuracy on `ids` with each role excluded in turn.

    Refits on the remaining judges (never freezes). `ids` must be eligible,
    i.e. valid under every refit; otherwise ValueError.
    """
    out: dict[str, float | None] = {}
    for role in roles:
        fit = fit_unfrozen(
            conn,
            experiment_id,
            len(roles) - 1,
            calib,
            thresh,
            cfg,
            frozenset({role}),
        )
        out[role] = _accuracy_on_ids(score_exp2(conn, fit, samples), ids)
    return out
