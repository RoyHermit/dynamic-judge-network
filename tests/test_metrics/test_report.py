"""compare_arms on small hand-built inputs (spec §6.6, §7)."""

from src.aggregation.core import MarginChoice
from src.experiments.config import Exp1Config, Pricing
from src.experiments.pipeline import ArmFit
from src.metrics.core import Row
from src.metrics.report import arm_cost, compare_arms, render_markdown
from src.storage.reader import CallRow


def _fit(experiment_id: str, margin: float) -> ArmFit:
    choice = MarginChoice(margin=margin, achieved=1.0, reached=True)
    return ArmFit(
        experiment_id=experiment_id,
        n_expected=1,
        calibrator={"xs": [0.0], "values": [0.5]},
        margins={"1.00": choice, "0.80": choice, "0.60": choice},
    )


def _rows(spec) -> list[Row]:
    return [
        Row(input_id=f"i{k}", regime="trend", label=label, t_index=k, p=p)
        for k, (p, label) in enumerate(spec)
    ]


CFG = Exp1Config(bootstrap_resamples=50, bootstrap_block_len=2)


def test_common_valid_set_excludes_samples_invalid_in_either_arm():
    rows_a = _rows([(0.9, "HIGH"), (0.2, "LOW"), (None, "HIGH"), (0.8, "HIGH")])
    rows_c = _rows([(0.9, "HIGH"), (None, "LOW"), (0.8, "HIGH"), (0.3, "HIGH")])
    report = compare_arms(
        rows_a, rows_c, _fit("A", 0.1), _fit("C", 0.1), CFG, calls_a=[], calls_c=[]
    )
    assert report["n_common_valid"] == 2  # i0 and i3
    assert report["arms"]["A"]["invalid_rate"] == 0.25
    assert report["common"]["targets"]["0.80"]["A"]["accuracy"] == 1.0
    assert report["common"]["targets"]["0.80"]["C"]["accuracy"] == 0.5


def test_warning_when_invalid_rate_exceeds_threshold_and_no_common_samples_is_safe():
    rows_a = _rows([(None, "HIGH"), (None, "LOW")])
    rows_c = _rows([(0.9, "HIGH"), (0.1, "LOW")])
    report = compare_arms(
        rows_a, rows_c, _fit("A", 0.1), _fit("C", 0.1), CFG, calls_a=[], calls_c=[]
    )
    assert report["n_common_valid"] == 0
    assert any("invalid" in w for w in report["warnings"])
    assert report["common"]["targets"]["0.80"]["A"]["accuracy"] is None
    assert report["common"]["targets"]["0.80"]["diff_ci"] is None
    assert "invalid" in render_markdown(report)


def test_constant_probabilities_do_not_break_the_report():
    rows = _rows([(0.5, "HIGH"), (0.5, "LOW"), (0.5, "HIGH")])
    report = compare_arms(
        rows, rows, _fit("A", 0.0), _fit("C", 0.0), CFG, calls_a=[], calls_c=[]
    )
    assert report["arms"]["A"]["targets"]["0.80"]["accuracy"] is None
    assert report["arms"]["A"]["brier"] is not None


def test_arm_cost_uses_pricing_and_reports_missing_usage():
    calls = [
        CallRow(
            input_id="i1",
            stage_index=0,
            latency=1.0,
            status="success",
            token_usage={"input_tokens": 1_000_000, "output_tokens": 500_000},
        ),
        CallRow(input_id="i2", stage_index=0, latency=1.0, status="error"),
    ]
    cost = arm_cost(calls, Pricing(input_per_mtok=2.0, output_per_mtok=4.0))
    assert cost["cost_usd"] == 4.0 and cost["calls_without_usage"] == 1
    assert arm_cost(calls, None)["cost_usd"] is None


def test_calls_of_unevaluated_samples_are_excluded_from_cost_and_latency():
    rows = _rows([(0.9, "HIGH"), (0.2, "LOW")])
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    calls = [
        CallRow(
            input_id=f"i{k}",
            stage_index=0,
            latency=1.0,
            status="success",
            token_usage=usage,
        )
        for k in (0, 1, 7, 8, 9)  # i7-i9 belong to other splits
    ]
    cfg = CFG.model_copy(
        update={"pricing": Pricing(input_per_mtok=1.0, output_per_mtok=0.0)}
    )
    report = compare_arms(
        rows, rows, _fit("A", 0.1), _fit("C", 0.1), cfg, calls_a=calls, calls_c=calls
    )
    cost = report["arms"]["A"]["cost"]
    assert cost["cost_usd"] == 2.0  # only i0 and i1
    assert cost["cost_usd_per_input"] == 1.0


def test_markdown_shows_per_arm_quality_cost_and_matched_coverage():
    rows = _rows([(0.9, "HIGH"), (0.2, "LOW"), (0.8, "HIGH")])
    report = compare_arms(
        rows, rows, _fit("A", 0.1), _fit("C", 0.1), CFG, calls_a=[], calls_c=[]
    )
    text = render_markdown(report)
    for needle in (
        "brier",
        "log_loss",
        "invalid_rate",
        "cost_usd",
        "matched",
        "regime",
    ):
        assert needle in text
