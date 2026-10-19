"""Per-judge calibration, error correlation, disagreement, leave-one-out."""

import pytest
from helpers_exp1 import insert_judge_log

from src.aggregation.platt import PlattCalibrator
from src.data.schema import Sample
from src.experiments.exp2_config import Exp2Config
from src.metrics.core import Row
from src.metrics.diagnostics import (
    aligned_error_vectors,
    error_vector,
    fit_judge_platt,
    full_set_accuracy,
    judge_diagnostics,
    judge_rows,
    leave_one_out,
    mean_pairwise_correlation,
    pairwise_disagreement,
    residual_vectors,
    safe_correlation,
)
from src.storage import db
from src.storage.writer import SqliteStorageWriter

EID = "e2"
IDENTITY = PlattCalibrator(intercept=0.0, slope=1.0, fallback=None, base_rate=0.5)
ROLES = ["role_a", "role_b", "role_c", "role_d", "role_e"]


def _row(i: int, label: str, p: float | None) -> Row:
    return Row(input_id=f"s{i}", regime="r", label=label, t_index=i, p=p)


def _rows(pattern: list[bool]) -> list[Row]:
    """Label alternates HIGH/LOW; pattern[i] says whether row i is correct."""
    out = []
    for i, ok in enumerate(pattern):
        label = "HIGH" if i % 2 == 0 else "LOW"
        right = 0.9 if label == "HIGH" else 0.1
        out.append(_row(i, label, right if ok else 1.0 - right))
    return out


def _sample(iid: str, label: str, split: str, t: int = 0) -> Sample:
    return Sample(
        input_id=iid, state={}, label=label, split=split, regime="trend", t_index=t
    )


@pytest.fixture
async def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    await SqliteStorageWriter(c).record_experiment(EID, {"a": 1})
    return c


def _answer(conn, iid: str, judge: str, value: float) -> None:
    insert_judge_log(conn, EID, iid, judge, value=value, call_id=f"{iid}-{judge}")


def test_constant_error_vector_is_undefined():
    a, b = _rows([True] * 6), _rows([True] * 6)
    ea, eb = error_vector(a), error_vector(b)
    assert safe_correlation(ea, eb) is None
    assert mean_pairwise_correlation([ea, eb]) is None
    assert safe_correlation([1.0], [1.0]) is None


def test_identical_errors_correlate_one():
    pat = [True, False, True, True, False, True, False, True]
    ea = error_vector(_rows(pat))
    assert safe_correlation(ea, ea) == pytest.approx(1.0)
    x = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
    y = [0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1]
    assert abs(safe_correlation(x, y)) < 0.1
    assert mean_pairwise_correlation([ea, ea, ea]) == pytest.approx(1.0)


def test_mean_pairwise_ignores_undefined_pairs():
    pat = [True, False, True, True, False, True]
    ea = [float(v) for v in error_vector(_rows(pat))]
    const = [0.0] * len(ea)
    assert mean_pairwise_correlation([ea, ea, const]) == pytest.approx(1.0)


async def test_per_judge_calibration_changes_error_definition(conn):
    calib = []
    for i in range(6):
        low, high = f"c{i}l", f"c{i}h"
        _answer(conn, low, "role_a", 0.05 + 0.01 * i)
        _answer(conn, high, "role_a", 0.30 + 0.02 * i)
        calib += [_sample(low, "LOW", "calib"), _sample(high, "HIGH", "calib")]
    # overlap so the fit is not perfectly separated (which would fall back)
    _answer(conn, "c_ol", "role_a", 0.34)
    _answer(conn, "c_oh", "role_a", 0.12)
    calib += [_sample("c_ol", "LOW", "calib"), _sample("c_oh", "HIGH", "calib")]
    platt = fit_judge_platt(conn, EID, calib, "role_a", 0.01)
    assert platt.fallback is None
    test = []
    for i in range(4):
        _answer(conn, f"t{i}l", "role_a", 0.08)
        _answer(conn, f"t{i}h", "role_a", 0.35)
        test += [_sample(f"t{i}l", "LOW", "test", 2 * i)]
        test += [_sample(f"t{i}h", "HIGH", "test", 2 * i + 1)]
    cal_rows = judge_rows(conn, EID, test, platt, "role_a")
    raw_rows = judge_rows(conn, EID, test, IDENTITY, "role_a")
    assert sum(error_vector(cal_rows)) == 0
    assert len(set(error_vector(cal_rows))) == 1
    # raw p < 0.5 everywhere: every HIGH is wrong, so raw errors are not all zero
    assert sum(error_vector(raw_rows)) == 4
    assert all(r.p is not None for r in cal_rows)
    assert judge_diagnostics(cal_rows).accuracy == 1.0


async def test_judge_rows_none_when_judge_missing(conn):
    _answer(conn, "x", "role_a", 0.7)
    _answer(conn, "y", "role_b", 0.7)
    samples = [_sample("x", "HIGH", "test"), _sample("y", "HIGH", "test", 1)]
    rows = judge_rows(conn, EID, samples, IDENTITY, "role_a")
    assert rows[0].p is not None and rows[1].p is None
    diag = judge_diagnostics(rows)
    assert diag.accuracy == 1.0 and diag.brier is not None
    assert judge_diagnostics([_row(0, "HIGH", None)]).accuracy is None


def test_aligned_vectors_use_common_valid_ids_in_time_order():
    a = [_row(2, "HIGH", 0.9), _row(0, "LOW", 0.2), _row(1, "HIGH", None)]
    b = [_row(0, "LOW", 0.6), _row(1, "HIGH", 0.9), _row(2, "HIGH", 0.8)]
    errs = aligned_error_vectors({"a": a, "b": b})
    assert errs == {"a": [0.0, 0.0], "b": [1.0, 0.0]}
    res = residual_vectors({"a": a, "b": b})
    assert res["a"] == pytest.approx([0.2, -0.1])
    assert res["b"] == pytest.approx([0.6, -0.2])


def test_disagreement_symmetric_and_in_unit_interval():
    rows = {
        "a": _rows([True, True, False, True]),
        "b": _rows([True, False, False, True]),
        "c": _rows([False, False, True, True]),
    }
    d = pairwise_disagreement(rows)
    assert set(d) == {("a", "b"), ("a", "c"), ("b", "c")}
    assert all(0.0 <= v <= 1.0 for v in d.values())
    assert d[("a", "b")] == pytest.approx(0.25)
    assert pairwise_disagreement({"b": rows["b"], "a": rows["a"]}) == {
        ("a", "b"): d[("a", "b")]
    }


async def test_leave_one_out_matches_manual_mean(conn):
    calib, thresh, test = [], [], []
    for split, bucket in (("calib", calib), ("thresh", thresh)):
        for i in range(4):
            for lab, v in (("LOW", 0.2), ("HIGH", 0.8)):
                iid = f"{split}{i}{lab}"
                for r in ROLES:
                    _answer(conn, iid, r, v)
                bucket.append(_sample(iid, lab, split))
        for lab, v in (("LOW", 0.7), ("HIGH", 0.3)):  # overlap: no perfect separation
            iid = f"{split}_ov{lab}"
            for r in ROLES:
                _answer(conn, iid, r, v)
            bucket.append(_sample(iid, lab, split))
    spec = [
        ("t0", "LOW", {r: 0.2 for r in ROLES}),
        ("t1", "HIGH", {r: 0.8 for r in ROLES}),
        ("t2", "LOW", {**{r: 0.45 for r in ROLES}, "role_a": 0.95}),
    ]
    for i, (iid, lab, vals) in enumerate(spec):
        for r, v in vals.items():
            _answer(conn, iid, r, v)
        test.append(_sample(iid, lab, "test", i))
    ids = [s.input_id for s in test]
    cfg = Exp2Config()
    loo = leave_one_out(conn, EID, ROLES, calib, thresh, test, cfg, ids)
    assert loo["role_a"] == pytest.approx(1.0)
    for r in ROLES[1:]:
        assert loo[r] == pytest.approx(2 / 3)
    assert full_set_accuracy(conn, EID, len(ROLES), calib, thresh, test, cfg, ids) == (
        pytest.approx(2 / 3)
    )


async def test_leave_one_out_rejects_invalid_id(conn):
    _answer(conn, "a", "role_a", 0.5)
    s = [_sample("a", "HIGH", "calib")]
    with pytest.raises(ValueError):
        leave_one_out(conn, EID, ["role_a", "role_b"], s, s, s, Exp2Config(), ["a"])
