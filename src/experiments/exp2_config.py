"""Experiment 2 configuration (role decomposition; spec §7, §9)."""

from __future__ import annotations

from pydantic import Field

from src.data.factory import DataConfig
from src.data.synthetic import SyntheticConfig
from src.experiments.config import Exp1Config

EXP2_SPLIT_SIZES: dict[str, int] = {
    "pilot": 30,
    "calib": 150,
    "thresh": 150,
    "test": 600,
    "test_shift": 300,
}


def _default_data() -> DataConfig:
    return SyntheticConfig(seed=11, split_sizes=dict(EXP2_SPLIT_SIZES))


class Exp2Config(Exp1Config):
    """Exp1 settings with Exp2 defaults plus calibration/pilot knobs."""

    study_id: str = "exp2"
    db_path: str = "workspace/exp2.db"
    data: DataConfig = Field(default_factory=_default_data)
    platt_l2: float = Field(default=0.01, ge=0)  # L2 strength for Platt scaling
    min_gain: float = Field(default=0.03, ge=0)  # frozen; do not tune
    degenerate_std: float = Field(default=0.01, gt=0)  # min std of an indicator
    pilot_invalid_max: float = Field(default=0.05, ge=0, le=1)
