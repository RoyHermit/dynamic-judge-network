"""Seeded synthetic price generator (spec §4.2-4.4, §4.7)."""

from __future__ import annotations

import hashlib
import math
import random

from pydantic import BaseModel, Field, model_validator

from src.data.schema import SPLITS, GeneratedData, Regime, Sample, Split


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


def _default_sizes() -> dict[Split, int]:
    # Development defaults only; real sizes are set after the pilot (spec §4.4).
    return {"pilot": 30, "calib": 200, "thresh": 200, "test": 300, "test_shift": 300}


class SyntheticConfig(BaseModel):
    seed: int = 0
    window: int = Field(default=60, ge=2)  # W
    horizon: int = Field(default=5, ge=1)  # H
    stride: int = Field(default=5, ge=1)
    epsilon: float = Field(default=1e-4, ge=0)
    embargo: int | None = None  # defaults to window + horizon
    segment_len: int = Field(default=200, ge=1)
    start_price: float = Field(default=100.0, gt=0)
    split_sizes: dict[Split, int] = Field(default_factory=_default_sizes)
    shift_vol_multiplier: float = Field(default=2.0, gt=0)
    regimes: dict[Regime, RegimeParams] = Field(default_factory=_default_regimes)

    @property
    def embargo_bars(self) -> int:
        return self.embargo if self.embargo is not None else self.window + self.horizon

    @model_validator(mode="after")
    def _validate(self) -> SyntheticConfig:
        if self.stride < self.horizon:
            raise ValueError("stride must be >= horizon so labels do not overlap")
        if self.embargo_bars < self.window + self.horizon:
            raise ValueError("embargo must be >= window + horizon")
        if set(self.split_sizes) != set(SPLITS) or min(self.split_sizes.values()) < 1:
            raise ValueError("split_sizes must give a size >= 1 for every split")
        return self


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


def dataset_id(cfg: SyntheticConfig) -> str:
    """Short stable id of the full generator configuration.

    Prefixing input ids with it keeps two datasets (e.g. different seeds)
    from colliding in the shared `inputs` table.
    """
    return hashlib.sha256(cfg.model_dump_json().encode()).hexdigest()[:8]


def generate(cfg: SyntheticConfig) -> GeneratedData:
    """Generate one continuous series cut into consecutive split blocks.

    Blocks are separated by `embargo_bars` discarded bars so that no
    window or label crosses a split boundary (spec §4.4).
    """
    rng = random.Random(cfg.seed)
    prefix = dataset_id(cfg)
    walk = _Walk(cfg, rng)
    bars: list[float] = []
    regimes: list[Regime] = []
    samples: list[Sample] = []
    excluded: dict[str, int] = {}

    for k, split in enumerate(SPLITS):
        walk.vol_mult = 1.0
        if k > 0:
            for _ in range(cfg.embargo_bars):
                close, regime = walk.step()
                bars.append(close)
                regimes.append(regime)
        walk.vol_mult = cfg.shift_vol_multiplier if split == "test_shift" else 1.0
        n_candidates = cfg.split_sizes[split]
        n_bars = (n_candidates - 1) * cfg.stride + cfg.window + cfg.horizon
        start = len(bars)
        for _ in range(n_bars):
            close, regime = walk.step()
            bars.append(close)
            regimes.append(regime)

        excluded[split] = 0
        for j in range(n_candidates):
            i = start + cfg.window - 1 + j * cfg.stride
            ret = math.log(bars[i + cfg.horizon] / bars[i])
            if abs(ret) <= cfg.epsilon:  # also excludes exact ties at epsilon=0
                excluded[split] += 1
                continue
            samples.append(
                Sample(
                    input_id=f"{prefix}-{split}-{i:06d}",
                    state={
                        "bars": [round(b, 4) for b in bars[i - cfg.window + 1 : i + 1]]
                    },
                    label="HIGH" if ret > 0 else "LOW",
                    split=split,
                    regime=regimes[i],
                    t_index=i,
                )
            )
    return GeneratedData(samples=samples, excluded=excluded, bars=bars)


class SyntheticSource:
    """DataSource backed by the seeded generator."""

    def __init__(self, cfg: SyntheticConfig) -> None:
        self.config = cfg
        self.data = generate(cfg)

    def samples(self, split: Split) -> list[Sample]:
        return [s for s in self.data.samples if s.split == split]
