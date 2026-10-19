"""Experiment 2 fit/score pipeline (Platt primary, isotonic sensitivity)."""

import json

import pytest
from helpers_exp1 import insert_judge_log

from src.data.schema import Sample
from src.experiments.exp2_config import Exp2Config
from src.experiments.exp2_pipeline import (
    fit_exp2_arm,
    fit_unfrozen,
    score_exp2,
    subset_means,
)
from src.storage import db
from src.storage.writer import SqliteStorageWriter

ROLES = ["role_trend", "role_volatility", "role_reversion", "role_momentum"]
EID = "e2"


def _sample(iid: str, label: str, split: str = "calib") -> Sample:
    return Sample(
        input_id=iid,
        state={},
        label=label,
        split=split,
        regime="trend",
        t_index=0,
    )


@pytest.fixture
async def env(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    writer = SqliteStorageWriter(conn)
    await writer.record_experiment(EID, {"a": 1})
    return conn, writer


def _answers(conn, iid: str, values: list[float], judges=ROLES) -> None:
    for j, v in zip(judges, values):
        insert_judge_log(conn, EID, iid, j, value=v, call_id=f"{iid}-{j}")


def _dataset(conn, prefix: str, split: str, flip: bool = False) -> list[Sample]:
    """Eight separable-with-overlap samples; mean tracks the label."""
    spec = [
        (0.1, "LOW"),
        (0.2, "LOW"),
        (0.3, "LOW"),
        (0.55, "LOW"),
        (0.45, "HIGH"),
        (0.6, "HIGH"),
        (0.7, "HIGH"),
        (0.9, "HIGH"),
    ]
    out = []
    for i, (m, lab) in enumerate(spec):
        if flip:
            lab = "LOW" if lab == "HIGH" else "HIGH"
        iid = f"{prefix}{i}"
        _answers(conn, iid, [m] * 4)
        out.append(_sample(iid, lab, split))
    return out


def test_partial_d_sample_is_invalid(env):
    conn, _ = env
    _answers(conn, "x", [0.5] * 4, ROLES[:4])
    samples = [_sample("x", "HIGH")]
    assert subset_means(conn, EID, 5, samples)["x"] is None


def test_exclude_judge_recomputes_from_stored_answers(env):
    conn, _ = env
    _answers(conn, "x", [0.2, 0.9, 0.4, 0.6])
    samples = [_sample("x", "HIGH")]
    m = subset_means(conn, EID, 4, samples, frozenset({"role_volatility"}))
    # n_expected=4 with one excluded: only 3 remain -> invalid
    assert m["x"] is None
    _answers(conn, "y", [0.2, 0.9, 0.4, 0.6])
    insert_judge_log(conn, EID, "y", "role_extra", value=0.8, call_id="y-extra")
    m = subset_means(
        conn, EID, 4, [_sample("y", "HIGH")], frozenset({"role_volatility"})
    )
    assert m["y"] == pytest.approx((0.2 + 0.4 + 0.6 + 0.8) / 4)


async def test_fit_records_platt_fallback(env):
    conn, writer = env
    calib = []
    for i in range(4):
        _answers(conn, f"c{i}", [0.5] * 4)
        calib.append(_sample(f"c{i}", "HIGH" if i % 2 else "LOW"))
    thresh = _dataset(conn, "t", "thresh")
    fit = await fit_exp2_arm(conn, writer, EID, 4, calib, thresh, Exp2Config())
    assert fit.platt.fallback == "constant_input"
    frozen = json.loads(
        conn.execute("SELECT config_json FROM experiments").fetchone()[0]
    )
    assert frozen["frozen"]["fit"]["platt"]["fallback"] == "constant_input"


async def test_degenerate_fit_refused_by_default(env):
    conn, writer = env
    calib = [_sample("none", "HIGH")]
    thresh = _dataset(conn, "t", "thresh")
    cfg = Exp2Config()
    with pytest.raises(ValueError):
        await fit_exp2_arm(conn, writer, EID, 4, calib, thresh, cfg)
    cfg_json = json.loads(
        conn.execute("SELECT config_json FROM experiments").fetchone()[0]
    )
    assert "frozen" not in cfg_json
    fit = await fit_exp2_arm(
        conn, writer, EID, 4, calib, thresh, cfg, allow_degenerate=True
    )
    assert fit.degenerate
    rows = score_exp2(conn, fit, thresh)
    assert all(r.p is None for r in rows)


async def test_freeze_cannot_be_overwritten(env):
    conn, writer = env
    calib = _dataset(conn, "c", "calib")
    thresh = _dataset(conn, "t", "thresh")
    await fit_exp2_arm(conn, writer, EID, 4, calib, thresh, Exp2Config())
    with pytest.raises(ValueError):
        await fit_exp2_arm(conn, writer, EID, 4, calib, thresh, Exp2Config())


async def test_isotonic_is_sensitivity_only(env):
    conn, writer = env
    calib = _dataset(conn, "c", "calib")
    thresh = _dataset(conn, "t", "thresh")
    fit = await fit_exp2_arm(conn, writer, EID, 4, calib, thresh, Exp2Config())
    platt = [r.p for r in score_exp2(conn, fit, thresh)]
    iso = [r.p for r in score_exp2(conn, fit, thresh, calibrator="isotonic")]
    assert platt != iso
    cfg = Exp2Config()
    assert set(fit.margins) == {cfg.target_key(t) for t in cfg.coverage_targets}


async def test_margins_use_thresh_not_calib(env):
    conn, _ = env
    cfg = Exp2Config()
    calib = _dataset(conn, "c", "calib")
    thresh = _dataset(conn, "t", "thresh")
    base = fit_unfrozen(conn, EID, 4, calib, thresh, cfg, frozenset())
    flipped_thresh = [
        s.model_copy(update={"label": "LOW" if s.label == "HIGH" else "HIGH"})
        for s in thresh
    ]
    same = fit_unfrozen(conn, EID, 4, calib, flipped_thresh, cfg, frozenset())
    assert same.platt == base.platt
    flipped_calib = [
        s.model_copy(update={"label": "LOW" if s.label == "HIGH" else "HIGH"})
        for s in calib
    ]
    other = fit_unfrozen(conn, EID, 4, flipped_calib, thresh, cfg, frozenset())
    assert other.platt != base.platt
