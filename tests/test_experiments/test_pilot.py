"""Pilot variance statistics (spec §5.4)."""

from pathlib import Path

import pytest
from helpers_exp1 import insert_judge_log

from src.experiments.config import Exp1Config
from src.experiments.pilot import collect_replica_probs, pilot_stats
from src.storage import db

LABELS = {"i1": "HIGH", "i2": "LOW", "i3": "HIGH"}


def test_identical_replicas_are_negligible_and_perfectly_correlated():
    probs = {i: [0.7, 0.7, 0.7] for i in LABELS}
    stats = pilot_stats(probs, LABELS)
    assert stats.mean_std == 0.0
    assert stats.disagreement_rate == 0.0
    assert stats.error_correlation == pytest.approx(1.0)  # same errors every time
    assert stats.negligible is True


def test_constant_error_series_have_no_defined_correlation():
    labels = {"i1": "HIGH", "i2": "HIGH"}  # replicas are never wrong
    stats = pilot_stats({i: [0.7, 0.7] for i in labels}, labels)
    assert stats.error_correlation is None


def test_varied_replicas_are_not_negligible():
    probs = {
        "i1": [0.9, 0.2, 0.8],
        "i2": [0.1, 0.7, 0.3],
        "i3": [0.6, 0.4, 0.9],
    }
    stats = pilot_stats(probs, LABELS)
    assert stats.mean_std > 0.1
    assert stats.disagreement_rate > 0.5
    assert stats.negligible is False
    assert stats.n_inputs == 3


def test_inputs_with_fewer_than_two_replicas_are_ignored_and_empty_raises():
    stats = pilot_stats({"i1": [0.6, 0.7], "i2": [0.5]}, LABELS)
    assert stats.n_inputs == 1
    with pytest.raises(ValueError):
        pilot_stats({"i1": [0.5]}, LABELS)


def test_collect_replica_probs_stacks_experiments_over_common_inputs(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    insert_judge_log(conn, "A1", "i1", "hl_judge", value=0.6, call_id="c-a1-i1")
    insert_judge_log(conn, "A2", "i1", "hl_judge", value=0.8, call_id="c-a2-i1")
    insert_judge_log(conn, "A1", "i2", "hl_judge", value=0.4, call_id="c-a1-i2")
    assert collect_replica_probs(conn, ["A1", "A2"]) == {"i1": [0.6, 0.8]}


def test_example_config_loads():
    text = Path("configs/exp1.example.json").read_text()
    cfg = Exp1Config.model_validate_json(text)
    assert cfg.n_replicas == 5 and cfg.headline_coverage in cfg.coverage_targets


def test_bootstrap_block_must_cover_window_over_stride():
    from pydantic import ValidationError

    from src.data.synthetic import SyntheticConfig

    data = SyntheticConfig(window=120, stride=5)
    with pytest.raises(ValidationError):
        Exp1Config(data=data, bootstrap_block_len=12)  # needs >= 24
    assert Exp1Config(data=data, bootstrap_block_len=24).bootstrap_block_len == 24
