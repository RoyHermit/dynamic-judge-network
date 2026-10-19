"""Seeded synthetic price generator (spec §4.2-4.4, §4.7)."""

from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Literal

from pydantic import BaseModel, Field

from src.data.schema import SPLITS, GeneratedData, Regime, Sample, Split
from src.data.windowing import WindowSpec, block_bars, cut_samples


class RegimeParams(BaseModel):
    drift: float = 0.0  # per-bar log-return drift (sign drawn per segment)
    ou_rate: float = 0.0  # mean-reversion strength per bar
    vol: float = 0.01  # per-bar log-return noise


def _default_regimes() -> dict[Regime, RegimeParams]:
    return {
        "trend": RegimeParams(drift=0.002, vol=0.01),
        "mean_reversion": RegimeParams(ou_rate=0.15, vol=0.01),
        "random_walk": RegimeParams(vol=0.01),
        "high_noise": RegimeParams(drift=0.0004, vol=0.04),
    }


class SyntheticConfig(WindowSpec):
    source: Literal["synthetic"] = "synthetic"
    seed: int = 0
    segment_len: int = Field(default=200, ge=1)
    start_price: float = Field(default=100.0, gt=0)
    shift_vol_multiplier: float = Field(default=2.0, gt=0)
    regimes: dict[Regime, RegimeParams] = Field(default_factory=_default_regimes)


class _Walk:
    """Log-price walk that cycles through regime segments."""

    def __init__(self, cfg: SyntheticConfig, rng: random.Random) -> None:
        self._cfg = cfg
        self._rng = rng
        self._order: list[Regime] = list(cfg.regimes)
        self._segment = -1
        self._left = 0
        self._x = math.log(cfg.start_price)
        self._regime: Regime = self._order[0]
        self._sign = 1
        self._anchor = self._x
        self.vol_mult = 1.0

    def _new_segment(self) -> None:
        self._segment += 1
        self._regime = self._order[self._segment % len(self._order)]
        self._left = self._cfg.segment_len
        self._sign = self._rng.choice((-1, 1))
        self._anchor = self._x

    def step(self) -> tuple[float, Regime]:
        if self._left == 0:
            self._new_segment()
        self._left -= 1
        p = self._cfg.regimes[self._regime]
        noise = p.vol * self.vol_mult * self._rng.gauss(0.0, 1.0)
        if self._regime == "mean_reversion":
            ret = -p.ou_rate * (self._x - self._anchor) + noise
        elif self._regime == "random_walk":
            ret = noise
        else:  # trend and high_noise share a signed drift
            ret = self._sign * p.drift + noise
        self._x += ret
        return math.exp(self._x), self._regime


def _canonical(cfg: SyntheticConfig) -> str:
    payload = cfg.model_dump(mode="json")
    payload.pop("source", None)  # keeps ids of data generated before `source` existed
    # Regime order changes the generated series, so keep it as an ordered
    # list; every other dict is key-sorted so cosmetic reordering of e.g.
    # split_sizes does not change the dataset identity.
    payload["regimes"] = [[name, p] for name, p in payload["regimes"].items()]
    return json.dumps(payload, sort_keys=True)


def dataset_id(cfg: SyntheticConfig) -> str:
    """Short stable id of the full generator configuration.

    Prefixing input ids with it keeps two datasets (e.g. different seeds)
    from colliding in the shared `inputs` table.
    """
    return hashlib.sha256(_canonical(cfg).encode()).hexdigest()[:8]


def same_dataset(a: dict, b: dict) -> bool:
    """True if two stored `SyntheticConfig` dumps generate the same data."""
    return dataset_id(SyntheticConfig.model_validate(a)) == dataset_id(
        SyntheticConfig.model_validate(b)
    )


def generate(cfg: SyntheticConfig) -> GeneratedData:
    """Generate one continuous series cut into consecutive split blocks.

    Blocks are separated by `embargo_bars` discarded bars so that no
    window or label crosses a split boundary (spec §4.4).
    """
    rng = random.Random(cfg.seed)
    walk = _Walk(cfg, rng)
    bars: list[float] = []
    regimes: list[Regime] = []
    starts: dict[Split, int] = {}

    for k, split in enumerate(SPLITS):
        walk.vol_mult = 1.0
        if k > 0:
            for _ in range(cfg.embargo_bars):
                close, regime = walk.step()
                bars.append(close)
                regimes.append(regime)
        walk.vol_mult = cfg.shift_vol_multiplier if split == "test_shift" else 1.0
        starts[split] = len(bars)
        for _ in range(block_bars(cfg, split)):
            close, regime = walk.step()
            bars.append(close)
            regimes.append(regime)

    samples, excluded = cut_samples(bars, regimes, starts, cfg, dataset_id(cfg))
    return GeneratedData(samples=samples, excluded=excluded, bars=bars)


class SyntheticSource:
    """DataSource backed by the seeded generator."""

    def __init__(self, cfg: SyntheticConfig) -> None:
        self.config = cfg
        self.data = generate(cfg)

    @property
    def excluded(self) -> dict[str, int]:
        return self.data.excluded

    def samples(self, split: Split) -> list[Sample]:
        return [s for s in self.data.samples if s.split == split]
