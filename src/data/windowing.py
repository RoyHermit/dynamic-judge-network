"""Shared windowing, labelling and split layout for price-series sources.

Both the synthetic generator and the public-data loader cut samples from a
close-price series the same way (spec §4.1, §4.3, §4.4).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

from src.data.schema import SPLITS, Regime, Sample, Split


def default_sizes() -> dict[Split, int]:
    # Development defaults only; real sizes are set after the pilot (spec §4.4).
    return {"pilot": 30, "calib": 200, "thresh": 200, "test": 300, "test_shift": 300}


class WindowSpec(BaseModel):
    """Window, horizon, stride, tie rule, embargo and split sizes."""

    window: int = Field(default=60, ge=2)  # W
    horizon: int = Field(default=5, ge=1)  # H
    stride: int = Field(default=5, ge=1)
    epsilon: float = Field(default=1e-4, ge=0)
    embargo: int | None = None  # defaults to window + horizon
    split_sizes: dict[Split, int] = Field(default_factory=default_sizes)

    @property
    def embargo_bars(self) -> int:
        return self.embargo if self.embargo is not None else self.window + self.horizon

    @model_validator(mode="after")
    def _validate_window(self) -> WindowSpec:
        if self.stride < self.horizon:
            raise ValueError("stride must be >= horizon so labels do not overlap")
        if self.embargo_bars < self.window + self.horizon:
            raise ValueError("embargo must be >= window + horizon")
        if set(self.split_sizes) != set(SPLITS) or min(self.split_sizes.values()) < 1:
            raise ValueError("split_sizes must give a size >= 1 for every split")
        return self


def block_bars(spec: WindowSpec, split: Split) -> int:
    """Number of bars the candidates of `split` span."""
    return (spec.split_sizes[split] - 1) * spec.stride + spec.window + spec.horizon


def total_bars(spec: WindowSpec) -> int:
    """Bars needed for all splits, including the embargo gaps between them."""
    return sum(block_bars(spec, s) for s in SPLITS) + spec.embargo_bars * (
        len(SPLITS) - 1
    )


def cut_samples(
    bars: list[float],
    regimes: list[Regime],
    starts: dict[Split, int],
    spec: WindowSpec,
    prefix: str,
) -> tuple[list[Sample], dict[str, int]]:
    """Cut labelled samples from `bars`; ties are excluded and counted."""
    samples: list[Sample] = []
    excluded: dict[str, int] = {}
    for split in SPLITS:
        excluded[split] = 0
        for j in range(spec.split_sizes[split]):
            i = starts[split] + spec.window - 1 + j * spec.stride
            ret = math.log(bars[i + spec.horizon] / bars[i])
            if abs(ret) <= spec.epsilon:  # also excludes exact ties at epsilon=0
                excluded[split] += 1
                continue
            samples.append(
                Sample(
                    input_id=f"{prefix}-{split}-{i:06d}",
                    state={
                        "bars": [round(b, 4) for b in bars[i - spec.window + 1 : i + 1]]
                    },
                    label="HIGH" if ret > 0 else "LOW",
                    split=split,
                    regime=regimes[i],
                    t_index=i,
                )
            )
    return samples, excluded
