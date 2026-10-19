"""Experiment 1 configuration (recorded into `experiments.config_json`)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.data.factory import DataConfig
from src.data.synthetic import SyntheticConfig


class Pricing(BaseModel):
    """USD per million tokens; provenance is kept next to the values."""

    input_per_mtok: float
    output_per_mtok: float
    source: str = ""


class Exp1Config(BaseModel):
    study_id: str = "exp1"
    db_path: str = "workspace/exp1.db"
    data: DataConfig = Field(default_factory=SyntheticConfig)
    n_replicas: int = Field(default=5, ge=1)
    model: str | None = None
    extra_body: dict[str, Any] | None = None
    pricing: Pricing | None = None
    sample_concurrency: int = Field(default=1, ge=1)
    coverage_targets: list[float] = Field(default_factory=lambda: [1.0, 0.8, 0.6])
    headline_coverage: float = 0.8
    margin_step: float = Field(default=0.005, gt=0)
    logloss_delta: float = Field(default=1e-6, gt=0)
    bootstrap_block_len: int = Field(default=12, ge=1)  # >= window / stride
    bootstrap_resamples: int = Field(default=1000, ge=1)
    bootstrap_seed: int = 0
    invalid_warn_rate: float = 0.05

    @model_validator(mode="after")
    def _validate(self) -> Exp1Config:
        if self.headline_coverage not in self.coverage_targets:
            raise ValueError("headline_coverage must be one of coverage_targets")
        needed = -(-self.data.window // self.data.stride)  # ceil(window / stride)
        if self.bootstrap_block_len < needed:
            raise ValueError(
                f"bootstrap_block_len must be >= window / stride ({needed}) so "
                "overlapping input windows stay in one block"
            )
        return self

    @staticmethod
    def target_key(target: float) -> str:
        """Stable string key for a coverage target."""
        return f"{target:.2f}"
