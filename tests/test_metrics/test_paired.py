import pytest

from src.experiments.exp2_config import Exp2Config
from src.metrics.core import Row
from src.metrics.paired import eligible_ids, full_coverage_correct, paired_accuracy_diff


def _row(i: int, label: str = "HIGH", p: float | None = 0.9) -> Row:
    return Row(input_id=f"s{i}", regime="r", label=label, t_index=i, p=p)


def _rows_with_accuracy(n: int, correct_pattern: list[bool]) -> list[Row]:
    """Rows whose correctness follows a repeating fixed pattern (label HIGH)."""
    return [
        _row(i, "HIGH", 0.9 if correct_pattern[i % len(correct_pattern)] else 0.1)
        for i in range(n)
    ]


def test_p_exactly_half_predicts_high():
    assert full_coverage_correct(_row(0, "HIGH", 0.5)) == 1
    assert full_coverage_correct(_row(0, "LOW", 0.5)) == 0
    with pytest.raises(ValueError):
        full_coverage_correct(_row(0, "HIGH", None))


def test_eligibility_is_intersection_over_llm_arms_only():
    n = 10
    arms = {
        "D": [_row(i) for i in range(n)],
        "Ap": [_row(i) for i in range(n)],
        "Ap5": [_row(i, p=None if i == 3 else 0.9) for i in range(n)],
        "L": [_row(i) for i in range(n)],
    }
    ids = eligible_ids(arms, ["D", "Ap", "Ap5"])
    assert "s3" not in ids and len(ids) == n - 1
    assert ids == sorted(ids, key=lambda s: int(s[1:]))
    # An always-valid L never shrinks the set, and a deterministic arm with
    # an invalid row is ignored when not listed.
    arms["L"][5] = _row(5, p=None)
    assert eligible_ids(arms, ["D", "Ap", "Ap5"]) == ids


def test_diff_ci_excludes_zero_for_clear_gain():
    cfg = Exp2Config()
    n = 400
    x = _rows_with_accuracy(n, [True, True, True, True, False])  # 0.8
    y = _rows_with_accuracy(n, [True, True, True, False, False])  # 0.6
    ids = [r.input_id for r in x]
    res = paired_accuracy_diff(x, y, ids, cfg)
    assert res.n == n
    assert res.diff == pytest.approx(0.2)
    assert res.acc_x == pytest.approx(0.8)
    assert res.acc_y == pytest.approx(0.6)
    assert res.ci is not None and res.ci[0] > 0


def test_small_or_empty_set_gives_none_ci():
    cfg = Exp2Config()
    k = 2 * cfg.bootstrap_block_len - 1
    x = _rows_with_accuracy(k, [True])
    y = _rows_with_accuracy(k, [False])
    res = paired_accuracy_diff(x, y, [r.input_id for r in x], cfg)
    assert res.ci is None and res.diff == pytest.approx(1.0)
    empty = paired_accuracy_diff(x, y, [], cfg)
    assert empty.n == 0
    assert empty.acc_x is None and empty.acc_y is None
    assert empty.diff is None and empty.ci is None


def test_pairing_uses_same_indices():
    cfg = Exp2Config()
    x = _rows_with_accuracy(300, [True, False, True, True, False])
    res = paired_accuracy_diff(x, list(x), [r.input_id for r in x], cfg)
    assert res.diff == 0
    # identical noisy arms: every resample pairs the same rows, so every
    # resampled difference is exactly 0 (an unpaired bootstrap would not be)
    assert res.ci == (0.0, 0.0)


def test_missing_or_invalid_ids_raise():
    cfg = Exp2Config()
    x = [_row(0), _row(1, p=None)]
    y = [_row(0), _row(1)]
    with pytest.raises(ValueError):
        paired_accuracy_diff(x, y, ["s0", "s1"], cfg)
    with pytest.raises(ValueError):
        paired_accuracy_diff(x, y, ["s0", "s9"], cfg)
