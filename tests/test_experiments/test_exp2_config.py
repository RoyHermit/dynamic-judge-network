"""Tests for the Experiment 2 configuration and example configs."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.data.synthetic import SyntheticConfig
from src.data.windowing import total_bars
from src.experiments.exp2_config import Exp2Config

CONFIGS = Path(__file__).resolve().parents[2] / "configs"
SPEC_SIZES = {"pilot": 30, "calib": 150, "thresh": 150, "test": 600, "test_shift": 300}


def _load(name: str) -> Exp2Config:
    return Exp2Config.model_validate_json((CONFIGS / name).read_text())


def test_example_configs_parse_with_spec_sizes() -> None:
    for name in ("exp2.example.json", "exp2-ecb.example.json"):
        cfg = _load(name)
        assert dict(cfg.data.split_sizes) == SPEC_SIZES
    syn = _load("exp2.example.json")
    assert isinstance(syn.data, SyntheticConfig)
    assert syn.data.seed != 0


def test_ecb_needs_6710_bars() -> None:
    cfg = _load("exp2-ecb.example.json")
    assert total_bars(cfg.data) == 6710


def test_min_gain_is_frozen_value() -> None:
    assert Exp2Config().min_gain == 0.03


def test_defaults() -> None:
    cfg = Exp2Config()
    assert cfg.study_id == "exp2"
    assert cfg.db_path == "workspace/exp2.db"
    assert cfg.data.seed == 11
    assert dict(cfg.data.split_sizes) == SPEC_SIZES
    assert cfg.headline_coverage == 0.8


def test_block_len_guard_inherited() -> None:
    with pytest.raises(ValidationError):
        Exp2Config(bootstrap_block_len=1)


def test_new_fields_validated() -> None:
    with pytest.raises(ValidationError):
        Exp2Config(platt_l2=-1.0)
    with pytest.raises(ValidationError):
        Exp2Config(degenerate_std=0.0)
