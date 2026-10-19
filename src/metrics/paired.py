"""Full-coverage paired accuracy comparison (spec §5). Pure, no I/O."""

from __future__ import annotations

from pydantic import BaseModel

from src.experiments.exp2_config import Exp2Config
from src.metrics.bootstrap import paired_block_ci
from src.metrics.core import Row


def full_coverage_correct(row: Row) -> int:
    """1 if the forced HIGH/LOW call (HIGH iff p >= 0.5) equals the label.

    SKIP is ignored on purpose: this is the full-coverage primary metric.
    """
    if row.p is None:
        raise ValueError(f"invalid row has no prediction: {row.input_id}")
    return int(("HIGH" if row.p >= 0.5 else "LOW") == row.label)


def eligible_ids(arms: dict[str, list[Row]], llm_arms: list[str]) -> list[str]:
    """Ids valid (p is not None) in every arm of `llm_arms`, ordered by t_index.

    Deterministic arms are excluded by not being listed in `llm_arms`.
    """
    valid: set[str] | None = None
    order: dict[str, int] = {}
    for name in llm_arms:
        ok = {r.input_id for r in arms[name] if r.p is not None}
        valid = ok if valid is None else valid & ok
        order.update({r.input_id: r.t_index for r in arms[name]})
    return sorted(valid or set(), key=lambda i: (order[i], i))


class PairedDiff(BaseModel):
    n: int
    acc_x: float | None
    acc_y: float | None
    diff: float | None
    ci: tuple[float, float] | None


def _correctness(rows: list[Row], ids: list[str]) -> list[int]:
    by_id = {r.input_id: r for r in rows}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise ValueError(f"ids missing from rows: {missing[:3]}")
    return [full_coverage_correct(by_id[i]) for i in ids]


def paired_accuracy_diff(
    x: list[Row], y: list[Row], ids: list[str], cfg: Exp2Config
) -> PairedDiff:
    """Accuracy of x minus y on `ids` (time-ordered by the caller), with a
    paired moving-block bootstrap CI. Raises ValueError on missing/invalid ids."""
    n = len(ids)
    if n == 0:
        return PairedDiff(n=0, acc_x=None, acc_y=None, diff=None, ci=None)
    cx, cy = _correctness(x, ids), _correctness(y, ids)
    acc_x, acc_y = sum(cx) / n, sum(cy) / n

    def stat(idx: list[int]) -> float:
        return sum(cx[i] - cy[i] for i in idx) / len(idx)

    ci = paired_block_ci(
        n, cfg.bootstrap_block_len, cfg.bootstrap_resamples, cfg.bootstrap_seed, stat
    )
    return PairedDiff(n=n, acc_x=acc_x, acc_y=acc_y, diff=acc_x - acc_y, ci=ci)
