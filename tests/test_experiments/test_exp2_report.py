"""Experiment 2 report: arms, paired comparisons, diagnostics, verdict, notes.

All answers are synthetic and inserted directly into a temporary DB from a
seeded `random.Random`; no real data and no API calls.
"""

import json
import random

import pytest
from helpers_exp1 import insert_call, insert_judge_log

from src.aggregation import logistic
from src.data.ecb import EcbCsvConfig
from src.data.schema import Sample, Split
from src.data.synthetic import SyntheticConfig, SyntheticSource
from src.experiments.exp2_arms import arm_spec, n_expected
from src.experiments.exp2_config import Exp2Config
from src.experiments.exp2_pipeline import fit_exp2_arm
from src.experiments.exp2_report import (
    CI_NOTE,
    COMPARISONS,
    ECB_NOTE,
    L_NOT_CONVERGED_NOTE,
    NO_VOL_NOTE,
    PRELIMINARY_NOTE,
    SECONDARY_NOTE,
    _verdict,
    build_report,
    load_frozen_fit,
    render_markdown,
    report_notes,
)
from src.experiments.exp2_report_sections import fmt_cell as _fmt
from src.experiments.verdict import evaluate_dataset
from src.features.indicators import ROLES
from src.metrics.paired import PairedDiff
from src.storage import db
from src.storage.writer import SqliteStorageWriter

SIZES = {"pilot": 3, "calib": 16, "thresh": 16, "test": 30, "test_shift": 24}
ALL_ARMS = ["A", "C", "Ap", "Ap5", "D"]
EXPECTED_KEYS = {
    "D-Ap",
    "D-Majority",
    "D-L",
    "D-M",
    "D-Ap5",
    "D-A",
    "D-C",
    "D-Const",
    "D-noVol vs D",
}


def _cfg(**kw) -> Exp2Config:
    data = kw.pop("data", None) or SyntheticConfig(seed=3, split_sizes=dict(SIZES))
    return Exp2Config(
        study_id="t2", data=data, bootstrap_resamples=200, **kw
    )  # block_len stays 12


def _judge_ids(arm: str) -> list[list[str]]:
    """Judge ids per call (one inner list per request)."""
    if arm == "A":
        return [["hl_judge"]]
    if arm == "C":
        return [[f"hl_judge#{k}" for k in range(5)]]
    if arm == "Ap":
        return [["ap_judge"]]
    if arm == "Ap5":
        return [[f"ap_judge#{k}"] for k in range(5)]
    return [[f"role_{r}"] for r in ROLES]


class _Relabelled:
    """Source wrapper that forces one label on a split (for edge cases)."""

    def __init__(self, inner: SyntheticSource, split: Split, label: str) -> None:
        self._inner, self._split, self._label = inner, split, label

    def samples(self, split: Split) -> list[Sample]:
        out = self._inner.samples(split)
        if split != self._split:
            return out
        return [s.model_copy(update={"label": self._label}) for s in out]


async def _build_db(
    tmp_path,
    cfg: Exp2Config,
    arms: list[str],
    constant_d: bool = False,
    drop: dict[str, set[str]] | None = None,
):
    """Insert seeded answers for every arm/split, then freeze each arm's fit.

    `drop[arm]` lists input ids whose first-stage judge log is omitted, which
    makes that sample invalid for the arm (too few valid answers).
    """
    drop = drop or {}
    conn = db.connect(tmp_path / "r.db")
    writer = SqliteStorageWriter(conn)
    source = SyntheticSource(cfg.data)
    rng = random.Random(7)
    strength = {"A": 0.05, "C": 0.08, "Ap": 0.1, "Ap5": 0.12, "D": 0.2}
    for arm in arms:
        eid = arm_spec(cfg.study_id, arm, cfg.n_replicas, 5).experiment_id
        await writer.record_experiment(eid, {"arm": arm})
        for split in ("calib", "thresh", "test", "test_shift"):
            for s in source.samples(split):
                for stage, judges in enumerate(_judge_ids(arm)):
                    call_id = insert_call(
                        conn,
                        eid,
                        s.input_id,
                        stage,
                        latency=0.2,
                        usage={"input_tokens": 100, "output_tokens": 10},
                    )
                    for j in judges:
                        sign = 1.0 if s.label == "HIGH" else -1.0
                        p = 0.5 + sign * strength[arm] + rng.gauss(0.0, 0.15)
                        if constant_d and arm == "D":
                            p = 0.3
                        if stage == 0 and s.input_id in drop.get(arm, set()):
                            continue
                        insert_judge_log(
                            conn,
                            eid,
                            s.input_id,
                            j,
                            value=min(max(p, 0.01), 0.99),
                            call_id=call_id,
                        )
        await fit_exp2_arm(
            conn,
            writer,
            eid,
            n_expected(arm, cfg.n_replicas),
            source.samples("calib"),
            source.samples("thresh"),
            cfg,
        )
    return conn, source


@pytest.fixture
async def full(tmp_path):
    cfg = _cfg()
    conn, source = await _build_db(tmp_path, cfg, ALL_ARMS)
    return conn, source, cfg


async def test_report_has_every_comparison_key(full):
    conn, source, cfg = full
    report = build_report(conn, cfg, source, "test", ALL_ARMS)
    assert set(COMPARISONS) == EXPECTED_KEYS
    assert set(report["comparisons"]) == EXPECTED_KEYS
    assert all(report["comparisons"][k] is not None for k in EXPECTED_KEYS)
    d_ap = report["comparisons"]["D-Ap"]
    assert d_ap["n"] == report["eligibility"]["n"] > 0
    assert d_ap["ci"] is not None  # n >= 2 * block_len
    for arm in [*ALL_ARMS, "L", "M", "Majority", "Const", "D-noVol"]:
        assert arm in report["arms"]
    d = report["arms"]["D"]
    for key in (
        "invalid_rate",
        "coverage_all",
        "accuracy_full",
        "matched_accuracy",
        "brier",
        "log_loss",
        "brier_raw",
        "log_loss_raw",
        "reliability",
        "isotonic",
        "cost",
        "latency_p50",
    ):
        assert key in d
    assert d["cost"]["input_tokens"] == 100 * len(ROLES) * len(source.samples("test"))
    verdict = report["verdict"]
    assert set(verdict) >= {"passed", "criteria", "attributable"}
    diag = report["diagnostics"]
    assert set(diag["judges"]) >= {f"role_{r}" for r in ROLES}
    assert set(diag["leave_one_out"]) == {f"role_{r}" for r in ROLES}
    assert report["secondary"] is False and report["preliminary"] is False


async def test_report_is_json_serialisable(full):
    conn, source, cfg = full
    report = build_report(conn, cfg, source, "test", ALL_ARMS)
    text = json.dumps(report)
    assert json.loads(text)["split"] == "test"


async def test_test_shift_report_has_only_secondary_arms(full):
    conn, source, cfg = full
    report = build_report(conn, cfg, source, "test_shift", ALL_ARMS)
    assert set(report["arms"]) == {"D", "Ap", "L", "M", "Majority"}
    assert set(report["comparisons"]) == {"D-Ap", "D-Majority", "D-L", "D-M"}
    assert report["verdict"] is None
    assert report["secondary"] is True
    assert SECONDARY_NOTE in report["notes"]
    assert "arms not reported on test_shift: A, C, Ap5" in report["notes"]
    md = render_markdown(report)
    assert SECONDARY_NOTE in md and "Verdict" not in md


async def test_preliminary_flag_is_normalised(full):
    conn, source, cfg = full
    report = build_report(conn, cfg, source, "test", ALL_ARMS, preliminary=True)
    assert report["preliminary"] is False
    assert report["eligibility"]["llm_arms"] == ["D", "Ap", "Ap5"]
    assert PRELIMINARY_NOTE not in report["notes"]
    assert "preliminary" not in render_markdown(report).splitlines()[0]
    shift = build_report(conn, cfg, source, "test_shift", ["D", "Ap"], preliminary=True)
    assert shift["preliminary"] is False


async def test_no_vol_reports_no_cost(full):
    conn, source, cfg = full
    report = build_report(conn, cfg, source, "test", ALL_ARMS)
    no_vol = report["arms"]["D-noVol"]
    assert no_vol["cost"] is None and no_vol["latency_p50"] is None
    assert NO_VOL_NOTE in report["notes"]
    render_markdown(report)  # renders without cost data


@pytest.fixture
async def with_invalid(tmp_path):
    """Some D samples and different Ap5 samples are invalid on test."""
    cfg = _cfg()
    test_ids = [s.input_id for s in SyntheticSource(cfg.data).samples("test")]
    drop = {"D": {test_ids[2], test_ids[3]}, "Ap5": {test_ids[10]}}
    conn, source = await _build_db(tmp_path, cfg, ALL_ARMS, drop=drop)
    return conn, source, cfg, test_ids, drop


async def test_eligibility_set_counts_invalid_samples(with_invalid):
    conn, source, cfg, test_ids, drop = with_invalid
    report = build_report(conn, cfg, source, "test", ALL_ARMS)
    expected = len(set(test_ids) - drop["D"] - drop["Ap5"])
    assert expected == len(test_ids) - 3
    assert report["n_labelled"] == len(test_ids)
    assert report["eligibility"]["n"] == expected
    for key in ("D-Ap", "D-Majority", "D-L", "D-M", "D-Ap5"):
        assert report["comparisons"][key]["n"] == expected, key
    assert report["comparisons"]["D-Ap"]["ci"] is not None


async def test_invalid_rate_and_coverage_all_count_invalid(with_invalid):
    conn, source, cfg, test_ids, drop = with_invalid
    report = build_report(conn, cfg, source, "test", ALL_ARMS)
    d = report["arms"]["D"]
    n_valid = len(test_ids) - len(drop["D"])
    assert d["n_valid"] == n_valid
    assert d["coverage_all"] == pytest.approx(n_valid / len(test_ids))
    assert d["coverage_all"] < 1
    assert d["invalid_rate"] == pytest.approx(1 - n_valid / len(test_ids))
    # at a stated margin coverage_all also divides by every labelled sample
    for t in d["targets"].values():
        assert t["coverage_all"] == pytest.approx(t["n_acted"] / len(test_ids))
    ap5 = report["arms"]["Ap5"]
    assert ap5["invalid_rate"] == pytest.approx(1 / len(test_ids))


async def test_verdict_matches_success_rule_on_report_comparisons(with_invalid):
    conn, source, cfg, _, _ = with_invalid
    report = build_report(conn, cfg, source, "test", ALL_ARMS)
    c = report["comparisons"]
    expected = evaluate_dataset(
        PairedDiff(**c["D-Ap"]),
        PairedDiff(**c["D-Majority"]),
        PairedDiff(**c["D-L"]),
        PairedDiff(**c["D-M"]),
        PairedDiff(**c["D-Ap5"]),
        cfg.min_gain,
    ).model_dump()
    assert report["verdict"] == expected
    assert report["verdict"]["attributable"] is not None


def _diff(diff: float, ci: tuple[float, float]) -> dict:
    return PairedDiff(n=30, acc_x=0.6, acc_y=0.6 - diff, diff=diff, ci=ci).model_dump()


def test_verdict_wires_each_comparison_to_its_criterion():
    """D-Ap passes and D-Ap5 fails: swapping them would flip both outcomes."""
    comparisons = {
        "D-Ap": _diff(0.1, (0.02, 0.2)),
        "D-Ap5": _diff(0.01, (-0.05, 0.06)),
        "D-Majority": _diff(0.1, (0.01, 0.2)),
        "D-L": _diff(0.1, (0.01, 0.2)),
        "D-M": _diff(0.1, (0.01, 0.2)),
    }
    verdict = _verdict(comparisons, _cfg())
    assert verdict["passed"] is True and verdict["attributable"] is False
    comparisons["D-L"] = _diff(0.1, (-0.01, 0.2))
    verdict = _verdict(comparisons, _cfg())
    assert verdict["passed"] is False and verdict["criteria"]["D>L"] is False
    assert verdict["criteria"]["D>M"] and verdict["criteria"]["D>Majority"]
    del comparisons["D-Ap"]
    with pytest.raises(ValueError, match="D-Ap"):
        _verdict(comparisons, _cfg())


async def test_missing_ap5_requires_preliminary(tmp_path):
    cfg = _cfg()
    arms = ["Ap", "D"]
    conn, source = await _build_db(tmp_path, cfg, arms)
    with pytest.raises(ValueError, match="preliminary"):
        build_report(conn, cfg, source, "test", arms)
    report = build_report(conn, cfg, source, "test", arms, preliminary=True)
    assert report["preliminary"] is True
    assert report["eligibility"]["llm_arms"] == ["D", "Ap"]
    assert report["comparisons"]["D-Ap5"] is None
    assert report["comparisons"]["D-A"] is None
    assert report["verdict"]["attributable"] is None
    assert any("excludes A'x5" in n for n in report["notes"])


async def test_undefined_correlation_is_none_in_report(tmp_path):
    cfg = _cfg()
    conn, source = await _build_db(tmp_path, cfg, ALL_ARMS, constant_d=True)
    # constant role answers + a single test label: every error vector is constant
    relabelled = _Relabelled(source, "test", "LOW")
    report = build_report(conn, cfg, relabelled, "test", ALL_ARMS)
    corr = report["diagnostics"]["correlation"]["D"]
    assert corr["mean_error"] is None
    assert corr["mean_residual"] is None
    assert all(v is None for v in corr["pairwise_error"].values())
    assert "null" in json.dumps(corr)
    assert report["diagnostics"]["correlation"]["Ap5"] is not None


async def test_constant_prediction_judges_have_undefined_correlations(tmp_path):
    cfg = _cfg()
    conn, source = await _build_db(tmp_path, cfg, ALL_ARMS, constant_d=True)
    # constant raw answers -> constant calibrated call; test labels stay mixed,
    # so the error vectors equal the label indicator (spurious +-1 if defined)
    assert {s.label for s in source.samples("test")} == {"HIGH", "LOW"}
    report = build_report(conn, cfg, source, "test", ALL_ARMS)
    diag = report["diagnostics"]
    corr = diag["correlation"]["D"]
    roles = sorted(f"role_{r}" for r in ROLES)
    assert corr["constant_prediction"] == roles
    assert all(v is None for v in corr["pairwise_error"].values())
    assert all(v is None for v in corr["pairwise_residual"].values())
    assert corr["mean_error"] is None
    for role in roles:
        assert diag["judges"][role]["constant_prediction"] is True
        assert diag["judges"][role]["platt_fallback"] == "constant_input"
    assert diag["correlation"]["Ap5"]["constant_prediction"] == []
    md = render_markdown(report)
    assert "constant_prediction" in md and "role_trend" in md
    assert "| role_trend |" in md and "constant_input" in md


async def test_report_marks_ecb_exploratory_and_ci_assumption(full, tmp_path):
    conn, source, _ = full
    ecb = EcbCsvConfig(path=str(tmp_path / "fake.csv"), split_sizes=dict(SIZES))
    assert ECB_NOTE in report_notes(ecb)
    assert CI_NOTE in report_notes(ecb)
    syn = SyntheticConfig(seed=3, split_sizes=dict(SIZES))
    assert ECB_NOTE not in report_notes(syn) and CI_NOTE in report_notes(syn)
    # end to end: the data config only drives the notes; samples come from source
    cfg = _cfg(data=ecb)
    md = render_markdown(build_report(conn, cfg, source, "test", ALL_ARMS))
    assert "ECB result is exploratory with respect to prior knowledge" in md
    assert (
        "bootstrap intervals condition on the frozen calibrator and margins "
        "and omit fitting uncertainty"
    ) in md


async def test_render_markdown_lists_sections(full):
    conn, source, cfg = full
    md = render_markdown(build_report(conn, cfg, source, "test", ALL_ARMS))
    for heading in ("## Arms", "## Comparisons", "## Diagnostics", "## Verdict"):
        assert heading in md
    assert "| D-Ap |" in md


async def test_load_frozen_fit_errors_are_clear(full):
    conn, _, _ = full
    with pytest.raises(ValueError, match="no experiment"):
        load_frozen_fit(conn, "missing-exp")
    await SqliteStorageWriter(conn).record_experiment("unfit", {"a": 1})
    with pytest.raises(ValueError, match="frozen"):
        load_frozen_fit(conn, "unfit")
    fit = load_frozen_fit(conn, "t2-D")
    assert fit.experiment_id == "t2-D" and fit.n_expected == len(ROLES)


async def test_markdown_shows_targets_reliability_tokens_latency_platt(full):
    conn, source, cfg = full
    report = build_report(conn, cfg, source, "test", ALL_ARMS)
    md = render_markdown(report)
    d = report["arms"]["D"]
    for heading in (
        "## Tokens, cost and latency",
        "## Platt calibration",
        "## SKIP analysis",
        "## Reliability",
    ):
        assert heading in md
    cost = d["cost"]
    assert cost["input_tokens"] == 30 * 5 * 100  # 30 test inputs x 5 calls
    assert (
        f"| D | {cost['input_tokens']} | {cost['output_tokens']} | 0 | n/a | n/a | "
        f"{_fmt(d['latency_p50'])} | {_fmt(d['latency_p95'])} |"
    ) in md
    platt = d["platt"]
    assert set(platt) == {"intercept", "slope", "fallback", "base_rate"}
    assert (
        f"| D | {_fmt(platt['intercept'])} | {_fmt(platt['slope'])} | "
        f"{_fmt(platt['base_rate'])} | {_fmt(platt['fallback'])} |"
    ) in md
    for key, t in d["targets"].items():
        assert (
            f"| D | {key} | {_fmt(t['margin'])} | {t['reached_target']} | "
            f"{_fmt(t['accuracy'])} |"
        ) in md
    bins = [b for b in d["reliability"] if b["n"]]
    assert bins
    for b in bins:
        assert f"| D | {b['bin']} | {b['n']} | {_fmt(b['mean_p'])} |" in md
    assert "| D-noVol | not reported |" in md


async def test_report_warns_when_logistic_l_did_not_converge(full, monkeypatch):
    conn, source, cfg = full
    report = build_report(conn, cfg, source, "test", ALL_ARMS)
    assert not any(L_NOT_CONVERGED_NOTE in n for n in report["notes"])
    monkeypatch.setattr(logistic, "MAX_ITER", 1)
    report = build_report(conn, cfg, source, "test", ALL_ARMS)
    assert any(L_NOT_CONVERGED_NOTE in n for n in report["notes"])
    assert L_NOT_CONVERGED_NOTE in render_markdown(report)
