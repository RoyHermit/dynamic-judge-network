"""Sample schema and DataSource seam for Experiment 1.

See docs/superpowers/specs/2026-10-15-experiment-1-fixed-judges-average-design.md §4.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel

Split = Literal["pilot", "calib", "thresh", "test", "test_shift"]
SPLITS: tuple[Split, ...] = ("pilot", "calib", "thresh", "test", "test_shift")
Regime = Literal["trend", "mean_reversion", "random_walk", "high_noise"]
Label = Literal["HIGH", "LOW"]


class Sample(BaseModel):
    """One labelled input. `state` holds past bars only (spec §4.1)."""

    input_id: str
    state: dict[str, Any]
    label: Label
    split: Split
    regime: Regime  # analysis metadata; never shown to a Judge
    t_index: int  # index of the last window bar; orders samples in time


class GeneratedData(BaseModel):
    samples: list[Sample]
    excluded: dict[str, int]  # per split: candidates dropped as ties
    bars: list[float]  # full close series (kept for tests and provenance)


class DataSource(Protocol):
    """Seam for later public-data loaders (spec §4.6)."""

    def samples(self, split: Split) -> list[Sample]: ...
