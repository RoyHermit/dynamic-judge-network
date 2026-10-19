"""Replica-variance statistics that gate the N/topology choice (spec §5.4).

The negligible-variance thresholds below were fixed before any pilot data
existed; do not tune them after looking at results.
"""

from __future__ import annotations

import itertools
import sqlite3
import statistics

from pydantic import BaseModel

from src.data.schema import Label
from src.storage.reader import load_probabilities

NEGLIGIBLE_MEAN_STD = 0.01
NEGLIGIBLE_DISAGREEMENT = 0.02


class PilotStats(BaseModel):
    n_inputs: int
    mean_std: float  # mean over inputs of the std across replicas
    disagreement_rate: float  # share of inputs whose replicas straddle 0.5
    error_correlation: float | None  # mean pairwise correlation of errors
    negligible: bool


def pilot_stats(
    probs_by_input: dict[str, list[float]], labels: dict[str, Label]
) -> PilotStats:
    rows = {i: v for i, v in probs_by_input.items() if len(v) >= 2 and i in labels}
    if not rows:
        raise ValueError("no inputs with at least two replicas")
    mean_std = statistics.fmean(statistics.pstdev(v) for v in rows.values())
    disagreement = statistics.fmean(
        float(len({p > 0.5 for p in v}) > 1) for v in rows.values()
    )
    n_replicas = min(len(v) for v in rows.values())
    errors = [
        [float((v[k] > 0.5) != (labels[i] == "HIGH")) for i, v in rows.items()]
        for k in range(n_replicas)
    ]
    corrs: list[float] = []
    for a, b in itertools.combinations(errors, 2):
        try:
            corrs.append(statistics.correlation(a, b))
        except statistics.StatisticsError:  # a constant series has no correlation
            continue
    return PilotStats(
        n_inputs=len(rows),
        mean_std=mean_std,
        disagreement_rate=disagreement,
        error_correlation=statistics.fmean(corrs) if corrs else None,
        negligible=mean_std < NEGLIGIBLE_MEAN_STD
        and disagreement < NEGLIGIBLE_DISAGREEMENT,
    )


def collect_replica_probs(
    conn: sqlite3.Connection, experiment_ids: list[str]
) -> dict[str, list[float]]:
    """Stack valid P(HIGH) per input across experiments.

    Passing `[A-run1, A-run2]` compares two repeat runs; passing
    `[C-batched]` compares its N replicas. Only inputs present in every
    experiment are kept.
    """
    per_experiment = [load_probabilities(conn, e) for e in experiment_ids]
    common = set.intersection(*(set(p) for p in per_experiment))
    return {
        i: [v for p in per_experiment for _, v in sorted(p[i].items())] for i in common
    }
