# Experiment 1: Fixed Judges + Average Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the data generator, replicated-Judge runner, offline aggregation, and metrics that establish baselines A (single Judge) and C (same Judge x N, fixed average) on identical data, with logs reusable for the dynamic DJN (E).

**Architecture:** Paid Jev execution (`src/experiments/runner.py`) writes every raw answer to the existing sqlite tables; aggregation, calibration, margins, metrics and reports are recomputed offline from storage. Data comes from a seeded synthetic generator behind a `DataSource` seam. A real-API pilot gates the final N/topology choice and is run by a human.

**Tech Stack:** Python 3.11+ (venv), pydantic 2, `typesafe-sdk` 0.7.2, sqlite3, pytest + pytest-asyncio, black, ruff. **No new dependencies** (isotonic regression, bootstrap and statistics are pure Python).

**Spec:** `docs/superpowers/specs/2026-10-15-experiment-1-fixed-judges-average-design.md` (read it first; section numbers below refer to it).

## Global Constraints

- Python 3.11+ with `pip` + `venv`; run tools as `venv/bin/python -m ...` / `venv/bin/pytest`.
- `typesafe-sdk` 0.7.2 via `JevStageExecutor`; no LiteLLM; `retry_count` stays `None`.
- Do **not** modify `requirements.txt` (adding a dependency needs human approval).
- Repo artifacts (code, comments, docstrings, docs) are English; chat is Japanese.
- Type hints on every function signature; docstrings on public functions; comments for non-obvious logic.
- Tests never call the real Jev API and never use real data; all data is generated from schemas (`mock-test-data` skill).
- Run `venv/bin/black src tests` and `venv/bin/ruff check src tests` before every commit.
- Work only on branch `feat/experiment-1-fixed-judges-average` (never `main`); never `git push`.
- Commit messages: `<type>: <summary>`, ending with the trailer line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Never read or print the local environment file or any credential; code must not take credentials as literals or arguments (the SDK reads its credential from the environment). Real API runs are human-only (Task 13).
- One `experiment_id` per scored arm (`<study>-A-run1`, `<study>-A-run2`, `<study>-C-batched`, `<study>-C-separate`); `decisions` is keyed `(experiment_id, input_id)`.
- Coverage is non-increasing in the margin; `p = 0.5` is always `SKIP`; margins use the largest grid value meeting the target (spec §6).
- Invalid samples (fewer than N valid answers) are never averaged and are counted separately from `SKIP`.

## Review Focus

Failure modes the spec implies that no single happy-path test would catch (each has a test in the named task):

1. Calibrated `p` exactly 0.5 (isotonic plateau) must give `SKIP`, never both `HIGH` and `LOW` (Task 8).
2. A Judge answer silently dropped by the SDK makes the C sample invalid instead of averaging survivors (Tasks 6, 8, 11).
3. Every usable answer missing for an arm: no crash in fit/score/report, empty acted sets yield `None` metrics (Tasks 9, 10, 11).
4. Constant probabilities (the negligible-variance case): single isotonic block, zero-variance correlation, degenerate margins must not divide by zero (Tasks 7, 8, 10).
5. Re-running after a partial run must not duplicate calls, inputs, or frozen settings; `freeze_config` refuses to overwrite (Tasks 5, 6, 11).

## File Structure

| File | Responsibility |
|---|---|
| `src/data/schema.py` | `Sample`, `GeneratedData`, `Split`/`Regime`/`Label` types, `DataSource` protocol |
| `src/data/synthetic.py` | `SyntheticConfig`, seeded `generate`, `SyntheticSource` |
| `src/data/baselines.py` | Majority, momentum, regime-aware reference rules |
| `src/judges/definitions/high_low.py` | `HighLowJudge` (Noul), `replica_index` |
| `src/judges/jev_executor.py` (modify) | Forward `model`/`extra_body`, record requested/returned model |
| `src/storage/writer.py` (modify) | `record_experiment`, `freeze_config`, `record_input`, `record_decision`, `mark_used` |
| `src/storage/reader.py` | Read helpers over the sqlite tables |
| `src/experiments/config.py` | `Exp1Config`, `Pricing` |
| `src/experiments/runner.py` | `ArmSpec`, `run_arm`, `finish_pending_interpretations` |
| `src/experiments/pilot.py` | Variance statistics and the predeclared negligible-variance rule |
| `src/aggregation/core.py` | Mean, isotonic calibrator, `decide`, margin selection |
| `src/metrics/core.py` | Row-level metrics, risk-coverage, interpolation |
| `src/metrics/bootstrap.py` | Moving-block paired bootstrap |
| `src/experiments/pipeline.py` | `fit_arm`, `score_rows`, `write_decisions` |
| `src/metrics/report.py` | `compare_arms`, `arm_cost`, `render_markdown` |
| `src/experiments/cli.py` | `run`, `pilot-stats`, `report` commands (thin) |

Tests mirror these paths under `tests/` with unique file names (the test folders have no `__init__.py`).

---

### Task 1: Data schema and synthetic generator

**Files:**
- Create: `src/data/__init__.py` (empty), `src/data/schema.py`, `src/data/synthetic.py`
- Test: `tests/test_data/test_synthetic.py`

**Interfaces:**
- Produces: `Sample(input_id, state, label, split, regime, t_index)`, `GeneratedData(samples, excluded, bars)`, `SPLITS`, `SyntheticConfig` (with `embargo_bars` property), `generate(cfg) -> GeneratedData`, `SyntheticSource(cfg).samples(split) -> list[Sample]`, `.data`, `.config`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_data/test_synthetic.py
"""Tests for the seeded synthetic generator (spec §4)."""

import math

import pytest
from pydantic import ValidationError

from src.data.schema import SPLITS
from src.data.synthetic import SyntheticConfig, SyntheticSource, generate

SIZES = {"pilot": 10, "calib": 40, "thresh": 40, "test": 40, "test_shift": 40}


def _cfg(**kwargs) -> SyntheticConfig:
    return SyntheticConfig(seed=1, split_sizes=SIZES, **kwargs)


def test_same_seed_is_deterministic_and_other_seed_differs():
    assert generate(_cfg()) == generate(_cfg())
    other = generate(SyntheticConfig(seed=2, split_sizes=SIZES))
    assert generate(_cfg()).bars != other.bars


def test_state_contains_only_past_bars_and_label_uses_future():
    cfg = _cfg()
    data = generate(cfg)
    assert data.samples
    for s in data.samples:
        t = s.t_index
        assert s.state["bars"] == [
            round(b, 4) for b in data.bars[t - cfg.window + 1 : t + 1]
        ]
        assert len(s.state["bars"]) == cfg.window
        assert set(s.state) == {"bars"}  # no regime or label leakage
        ret = math.log(data.bars[t + cfg.horizon] / data.bars[t])
        assert s.label == ("HIGH" if ret > 0 else "LOW")


def test_embargo_separates_consecutive_splits():
    cfg = _cfg()
    data = generate(cfg)
    by_split = {sp: [s.t_index for s in data.samples if s.split == sp] for sp in SPLITS}
    for a, b in zip(SPLITS, SPLITS[1:]):
        gap = (min(by_split[b]) - cfg.window + 1) - (max(by_split[a]) + cfg.horizon)
        assert gap >= cfg.embargo_bars


def test_ties_are_excluded_and_counted():
    cfg = _cfg(epsilon=10.0)  # every |return| is below epsilon
    data = generate(cfg)
    assert data.samples == []
    assert data.excluded == SIZES


def test_every_candidate_is_labelled_or_excluded():
    data = generate(_cfg())
    assert len(data.samples) + sum(data.excluded.values()) == sum(SIZES.values())


def test_stride_must_cover_horizon_and_embargo_must_cover_window_plus_horizon():
    with pytest.raises(ValidationError):
        SyntheticConfig(stride=1, horizon=5)
    with pytest.raises(ValidationError):
        SyntheticConfig(window=60, horizon=5, embargo=10)


def test_source_returns_split_samples_only():
    source = SyntheticSource(_cfg())
    assert {s.split for s in source.samples("calib")} == {"calib"}
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_data/test_synthetic.py -v`
Expected: FAIL (`ModuleNotFoundError: src.data.schema`).

- [ ] **Step 3: Implement**

```python
# src/data/__init__.py  (empty file)
```

```python
# src/data/schema.py
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
```

```python
# src/data/synthetic.py
"""Seeded synthetic price generator (spec §4.2-4.4, §4.7)."""

from __future__ import annotations

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


def generate(cfg: SyntheticConfig) -> GeneratedData:
    """Generate one continuous series cut into consecutive split blocks.

    Blocks are separated by `embargo_bars` discarded bars so that no
    window or label crosses a split boundary (spec §4.4).
    """
    rng = random.Random(cfg.seed)
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
            if abs(ret) < cfg.epsilon:
                excluded[split] += 1
                continue
            samples.append(
                Sample(
                    input_id=f"{split}-{i:06d}",
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
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_data/test_synthetic.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
venv/bin/black src tests && venv/bin/ruff check src tests
git add src/data tests/test_data
git commit -m "feat: Experiment 1の合成データ生成器とSample schemaを追加する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Reference baselines

**Files:**
- Create: `src/data/baselines.py`
- Test: `tests/test_data/test_baselines.py`

**Interfaces:**
- Consumes: `Sample`, `Label`, `Regime` from Task 1.
- Produces: `accuracy(preds, samples) -> float`, `majority_label(samples) -> Label`, `momentum_signal(state, lookback, sign) -> Label`, `MomentumRule(lookback, sign).predict(state)`, `fit_momentum(samples) -> MomentumRule`, `RegimeAwareRule.predict(sample)`, `fit_regime_aware(samples) -> RegimeAwareRule`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_data/test_baselines.py
"""Tests for the LLM-free reference rules (spec §4.5)."""

from src.data.baselines import (
    accuracy,
    fit_momentum,
    fit_regime_aware,
    majority_label,
    momentum_signal,
)
from src.data.schema import Sample
from src.data.synthetic import SyntheticConfig, generate


def _sample(bars, label, regime="trend", i=0) -> Sample:
    return Sample(
        input_id=f"s{i}",
        state={"bars": bars},
        label=label,
        split="calib",
        regime=regime,
        t_index=i,
    )


def test_majority_label_prefers_high_on_tie():
    flat = [1.0] * 60
    assert majority_label([_sample(flat, "LOW"), _sample(flat, "HIGH")]) == "HIGH"
    assert majority_label([_sample(flat, "LOW")]) == "LOW"


def test_momentum_signal_direction_and_sign():
    up = [float(k) for k in range(60)]
    assert momentum_signal({"bars": up}, 5, 1) == "HIGH"
    assert momentum_signal({"bars": up}, 5, -1) == "LOW"


def test_fit_momentum_learns_direction():
    up = [float(k) for k in range(60)]
    down = [float(60 - k) for k in range(60)]
    follow = [_sample(up, "HIGH", i=1), _sample(down, "LOW", i=2)]
    reverse = [_sample(up, "LOW", i=1), _sample(down, "HIGH", i=2)]
    assert fit_momentum(follow).sign == 1
    assert fit_momentum(reverse).sign == -1
    rule = fit_momentum(follow)
    assert accuracy([rule.predict(s.state) for s in follow], follow) == 1.0


def test_momentum_is_near_chance_on_random_walk():
    # Labels are independent increments, so a fixed rule is a martingale
    # difference sum: std ~ 0.5/sqrt(n). Doubles as a leak detector.
    cfg = SyntheticConfig(
        seed=3,
        split_sizes={
            "pilot": 5,
            "calib": 3000,
            "thresh": 5,
            "test": 5,
            "test_shift": 5,
        },
    )
    calib = [s for s in generate(cfg).samples if s.split == "calib"]
    walk = [s for s in calib if s.regime == "random_walk"]
    assert len(walk) > 300
    acc = accuracy([momentum_signal(s.state, 20, 1) for s in walk], walk)
    assert 0.42 <= acc <= 0.58


def test_regime_aware_fits_at_least_as_well_as_global_in_sample():
    cfg = SyntheticConfig(
        seed=4,
        split_sizes={
            "pilot": 5,
            "calib": 1500,
            "thresh": 5,
            "test": 5,
            "test_shift": 5,
        },
    )
    calib = [s for s in generate(cfg).samples if s.split == "calib"]
    global_rule = fit_momentum(calib)
    regime_rule = fit_regime_aware(calib)
    acc_global = accuracy([global_rule.predict(s.state) for s in calib], calib)
    acc_regime = accuracy([regime_rule.predict(s) for s in calib], calib)
    assert acc_regime >= acc_global
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_data/test_baselines.py -v`
Expected: FAIL (`ModuleNotFoundError: src.data.baselines`).

- [ ] **Step 3: Implement**

```python
# src/data/baselines.py
"""LLM-free reference rules (spec §4.5).

Parameters are fitted on the `calib` split only. The regime-aware rule is
a reference point, not a guaranteed upper bound.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import BaseModel

from src.data.schema import Label, Regime, Sample

# 59 keeps `bars[-1 - lookback]` inside the default 60-bar window.
LOOKBACKS = (5, 10, 20, 59)


def accuracy(preds: list[Label], samples: list[Sample]) -> float:
    """Fraction of predictions equal to the sample label."""
    if not samples:
        raise ValueError("accuracy needs at least one sample")
    return sum(p == s.label for p, s in zip(preds, samples)) / len(samples)


def majority_label(samples: list[Sample]) -> Label:
    """Most frequent label; ties go to HIGH."""
    high = sum(s.label == "HIGH" for s in samples)
    return "HIGH" if high >= len(samples) - high else "LOW"


def momentum_signal(state: dict[str, Any], lookback: int, sign: int) -> Label:
    """Follow (sign=+1) or fade (sign=-1) the move over `lookback` bars."""
    bars = state["bars"]
    up = bars[-1] - bars[-1 - lookback] > 0
    if sign < 0:
        up = not up
    return "HIGH" if up else "LOW"


class MomentumRule(BaseModel):
    lookback: int
    sign: int

    def predict(self, state: dict[str, Any]) -> Label:
        return momentum_signal(state, self.lookback, self.sign)


def fit_momentum(samples: list[Sample]) -> MomentumRule:
    """Pick (lookback, sign) with the best accuracy; first wins on ties."""
    best: tuple[float, MomentumRule] | None = None
    for lookback in LOOKBACKS:
        for sign in (1, -1):
            rule = MomentumRule(lookback=lookback, sign=sign)
            acc = accuracy([rule.predict(s.state) for s in samples], samples)
            if best is None or acc > best[0]:
                best = (acc, rule)
    assert best is not None
    return best[1]


class RegimeAwareRule(BaseModel):
    default: MomentumRule
    rules: dict[Regime, MomentumRule]

    def predict(self, sample: Sample) -> Label:
        return self.rules.get(sample.regime, self.default).predict(sample.state)


def fit_regime_aware(samples: list[Sample]) -> RegimeAwareRule:
    """Fit one momentum rule per regime (uses the regime label by design)."""
    grouped: dict[Regime, list[Sample]] = defaultdict(list)
    for s in samples:
        grouped[s.regime].append(s)
    return RegimeAwareRule(
        default=fit_momentum(samples),
        rules={regime: fit_momentum(group) for regime, group in grouped.items()},
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_data -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
venv/bin/black src tests && venv/bin/ruff check src tests
git add src/data tests/test_data
git commit -m "feat: majority・momentum・regime-awareの参照ルールを追加する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: High/Low Judge definition

**Files:**
- Create: `src/judges/definitions/high_low.py`
- Test: `tests/test_judges/test_high_low_judge.py`

**Interfaces:**
- Consumes: `Question`, `Answer`, `Decision`, `State` from `src/judges/interface.py`.
- Produces: `HighLowJudge(horizon, replica=None)` with `judge_id` `"hl_judge"` or `"hl_judge#<k>"`, `judge_version = "highlow-1.0"`; `replica_index(judge_id) -> int | None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_judges/test_high_low_judge.py
"""Tests for HighLowJudge (spec §5.1)."""

import math

import pytest

from src.judges.definitions.high_low import HighLowJudge, replica_index
from src.judges.interface import Answer, Judge


def _noul(p) -> Answer:
    return Answer(
        kind="noul", raw_value=p if p is not None else 0.0, raw_probability=p
    )


def test_satisfies_judge_protocol_and_ids():
    assert isinstance(HighLowJudge(horizon=5), Judge)
    assert HighLowJudge(5).judge_id == "hl_judge"
    assert HighLowJudge(5, replica=3).judge_id == "hl_judge#3"
    assert replica_index("hl_judge#3") == 3
    assert replica_index("hl_judge") is None


def test_to_question_is_noul_and_mentions_horizon():
    q = HighLowJudge(horizon=7).to_question({"bars": [1.0, 2.0]})
    assert q.kind == "noul"
    assert "7 bars" in q.prompt


def test_interpret_returns_probability_of_high():
    decision = HighLowJudge(5).interpret(_noul(0.73))
    assert decision.value == 0.73


@pytest.mark.parametrize("bad", [None, math.nan, -0.1, 1.2, math.inf])
def test_interpret_rejects_invalid_probability(bad):
    with pytest.raises(ValueError):
        HighLowJudge(5).interpret(_noul(bad))


def test_interpret_rejects_non_noul_answers():
    answer = Answer(kind="choice", raw_value="HIGH", raw_probability=0.9)
    with pytest.raises(ValueError):
        HighLowJudge(5).interpret(answer)
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_judges/test_high_low_judge.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# src/judges/definitions/high_low.py
"""High/Low Judge for Experiment 1 (spec §5.1).

Asks one Noul question and reads the Noul probability as P(HIGH). Choice
confidence is deliberately not used: it is the confidence of the selected
label, not P(HIGH), so averaging it would be wrong.
"""

from __future__ import annotations

import math

from src.judges.interface import Answer, Decision, Question, State


def replica_index(judge_id: str) -> int | None:
    """Parse `hl_judge#<k>`; return None for the un-replicated Judge."""
    _, sep, tail = judge_id.partition("#")
    return int(tail) if sep else None


class HighLowJudge:
    judge_version = "highlow-1.0"

    def __init__(self, horizon: int, replica: int | None = None) -> None:
        self.judge_id = "hl_judge" if replica is None else f"hl_judge#{replica}"
        self.judge_prompt_or_definition = (
            "Using only the price bars in the state (oldest first, the last "
            f"element is the latest close), is the close {horizon} bars after "
            "the last bar higher than the last bar's close? Answer with the "
            "probability that it is higher."
        )

    def to_question(self, state: State) -> Question:
        return Question(kind="noul", prompt=self.judge_prompt_or_definition)

    def interpret(self, answer: Answer) -> Decision:
        p = answer.raw_probability
        if (
            answer.kind != "noul"
            or p is None
            or isinstance(p, bool)
            or not math.isfinite(p)
            or not 0.0 <= p <= 1.0
        ):
            raise ValueError(f"invalid P(HIGH) answer: {answer!r}")
        return Decision(value=p)
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_judges -v`
Expected: PASS (new and existing).

- [ ] **Step 5: Commit**

```bash
venv/bin/black src tests && venv/bin/ruff check src tests
git add src/judges/definitions tests/test_judges
git commit -m "feat: NoulベースのHighLowJudgeを追加する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Executor forwards `model` / `extra_body` and records the returned model

**Files:**
- Modify: `src/judges/jev_executor.py` (constructor, `system_one` call, `token_usage`)
- Test: `tests/test_judges/test_jev_executor_options.py`

**Interfaces:**
- Consumes: existing `JevStageExecutor`.
- Produces: `JevStageExecutor(client, writer, *, model=None, extra_body=None)`; `CallRecord.token_usage` on success becomes `{"input_tokens", "output_tokens", "requested_model", "returned_model"}` (the `calls` table has no model column; the existing JSON column carries it, no migration).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_judges/test_jev_executor_options.py
"""Executor option forwarding and model provenance (spec §3.2, §5.4)."""

import typesafe_sdk as ts

from src.judges.definitions.high_low import HighLowJudge
from src.judges.jev_executor import JevStageExecutor


class CapturingClient:
    def __init__(self) -> None:
        self.kwargs: dict | None = None

    async def system_one(self, **kwargs):
        self.kwargs = kwargs
        return ts.SystemOneResponse(
            model="returned-model",
            usage=ts.Usage(input_tokens=3, output_tokens=1),
            answers={"hl_judge": ts.NoulAnswer(noul=0.6)},
        )


class NullWriter:
    async def record_call(self, call, raw_judge_records):
        pass

    async def record_interpretation(self, call_id, judge_id, decision, error):
        pass


async def test_model_and_extra_body_are_forwarded_and_model_recorded():
    client = CapturingClient()
    executor = JevStageExecutor(
        client, NullWriter(), model="m1", extra_body={"temperature": 1.0}
    )
    result = await executor.run_stage(
        state={"bars": [1.0]},
        judges=[HighLowJudge(5)],
        experiment_id="e",
        input_id="i",
        stage_index=0,
    )
    assert client.kwargs["model"] == "m1"
    assert client.kwargs["extra_body"] == {"temperature": 1.0}
    assert result.calls[0].token_usage == {
        "input_tokens": 3,
        "output_tokens": 1,
        "requested_model": "m1",
        "returned_model": "returned-model",
    }


async def test_options_are_omitted_when_not_set():
    client = CapturingClient()
    executor = JevStageExecutor(client, NullWriter())
    result = await executor.run_stage(
        state={"bars": [1.0]},
        judges=[HighLowJudge(5)],
        experiment_id="e",
        input_id="i",
        stage_index=0,
    )
    assert "model" not in client.kwargs and "extra_body" not in client.kwargs
    assert result.calls[0].token_usage["requested_model"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_judges/test_jev_executor_options.py -v`
Expected: FAIL (`unexpected keyword argument 'model'`).

- [ ] **Step 3: Implement**

In `src/judges/jev_executor.py`: add `from collections.abc import Mapping` to the imports; replace the constructor, the `system_one` call, and the `token_usage` block exactly as below.

```python
    def __init__(
        self,
        client: ts.AsyncTypeSafeClient,
        writer: StorageWriter,
        *,
        model: str | None = None,
        extra_body: Mapping[str, Any] | None = None,
    ) -> None:
        self._client = client
        self._writer = writer
        self._model = model
        self._extra_body = extra_body
```

```python
        # Options are only passed when set so clients that do not accept
        # them (and the SDK defaults) behave exactly as before.
        options: dict[str, Any] = {}
        if self._model is not None:
            options["model"] = self._model
        if self._extra_body is not None:
            options["extra_body"] = self._extra_body

        try:
            response = await self._client.system_one(
                state=state,
                questions={
                    judge_id: _to_provider_question(question)
                    for judge_id, question in questions.items()
                },
                **options,
            )
```

```python
        token_usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "requested_model": self._model,
            "returned_model": response.model,
        }
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_judges -v`
Expected: PASS. If an existing test asserts an exact `token_usage` dict, update that assertion to include the two new keys (this is the intended behavior change).

- [ ] **Step 5: Commit**

```bash
venv/bin/black src tests && venv/bin/ruff check src tests
git add src/judges/jev_executor.py tests/test_judges
git commit -m "feat: executorがmodel・extra_bodyを転送し返却modelを記録する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Writer extensions and storage reader

**Files:**
- Modify: `src/storage/writer.py` (add methods to `SqliteStorageWriter`)
- Create: `src/storage/reader.py`, `tests/conftest.py` (only if absent), `tests/test_storage/helpers_exp1.py`
- Test: `tests/test_storage/test_writer_exp1.py`, `tests/test_storage/test_reader.py`

**Interfaces:**
- Produces on `SqliteStorageWriter`: `record_experiment(experiment_id, config, aggregator_version=None)` (idempotent), `freeze_config(experiment_id, key, value)` (raises `ValueError` if key already frozen, `KeyError` if no experiment), `record_input(input_id, features, ground_truth, task_type="high_low")` (idempotent), `record_decision(*, experiment_id, input_id, aggregate_score, final_confidence, final_decision, is_correct, total_latency, early_stopped)`, `mark_used(experiment_id, input_id, judge_ids, used)`.
- Produces in `reader.py`: `CallRow`, `completed_units(conn, experiment_id) -> set[tuple[str, int]]`, `load_probabilities(conn, experiment_id) -> dict[str, dict[str, float]]` (valid P(HIGH) only), `load_calls(conn, experiment_id) -> list[CallRow]`, `pending_interpretations(conn, experiment_id) -> list[tuple[str, str, Answer]]`, `completion_latency(calls) -> dict[str, float]`.

- [ ] **Step 1: Write the failing tests and helpers**

`tests/conftest.py` makes the shared direct-SQL helper importable (the test folders have no `__init__.py`; `pythonpath = ["."]` already exposes `src`):

```python
# tests/conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "test_storage"))
```

```python
# tests/test_storage/helpers_exp1.py
"""Direct-SQL fixtures for reader/writer tests (no writer under test)."""

import json
import sqlite3


def insert_call(
    conn: sqlite3.Connection,
    experiment_id: str,
    input_id: str,
    stage_index: int = 0,
    status: str = "success",
    latency: float = 0.1,
    usage: dict | None = None,
    call_id: str | None = None,
) -> str:
    call_id = call_id or f"{experiment_id}-{input_id}-{stage_index}"
    conn.execute(
        "INSERT INTO calls (call_id, experiment_id, input_id, stage_index, executor,"
        " question_count, latency, retry_count, token_usage_json, status,"
        " error_message, timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            call_id,
            experiment_id,
            input_id,
            stage_index,
            "JevStageExecutor",
            1,
            latency,
            None,
            json.dumps(usage) if usage else None,
            status,
            None,
            "t",
        ),
    )
    conn.commit()
    return call_id


def insert_judge_log(
    conn: sqlite3.Connection,
    experiment_id: str,
    input_id: str,
    judge_id: str,
    value: float | None = None,
    error: str | None = None,
    call_id: str = "c1",
    raw_p: float = 0.5,
) -> None:
    raw = json.dumps({"kind": "noul", "raw_value": raw_p, "raw_probability": raw_p})
    conn.execute(
        "INSERT INTO judge_logs (call_id, experiment_id, input_id, judge_id,"
        " judge_version, judge_prompt_or_definition, question_json, raw_answer_json,"
        " judge_latency, timestamp, interpreted_value, interpret_error)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            call_id,
            experiment_id,
            input_id,
            judge_id,
            "v",
            "d",
            "{}",
            raw,
            0.1,
            "t",
            value,
            error,
        ),
    )
    conn.commit()
```

```python
# tests/test_storage/test_writer_exp1.py
"""Experiment 1 writer extensions (spec §3.2, §8)."""

import json

import pytest
from helpers_exp1 import insert_judge_log

from src.storage import db
from src.storage.writer import SqliteStorageWriter


@pytest.fixture
def env(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    return conn, SqliteStorageWriter(conn)


async def test_record_experiment_is_idempotent(env):
    conn, writer = env
    await writer.record_experiment("e1", {"a": 1})
    await writer.record_experiment("e1", {"a": 2})
    rows = conn.execute("SELECT config_json FROM experiments").fetchall()
    assert len(rows) == 1 and json.loads(rows[0][0]) == {"a": 1}


async def test_freeze_config_merges_and_refuses_overwrite(env):
    conn, writer = env
    await writer.record_experiment("e1", {"a": 1})
    await writer.freeze_config("e1", "fit", {"m": 0.1})
    cfg = json.loads(conn.execute("SELECT config_json FROM experiments").fetchone()[0])
    assert cfg["a"] == 1 and cfg["frozen"]["fit"] == {"m": 0.1}
    with pytest.raises(ValueError):
        await writer.freeze_config("e1", "fit", {"m": 0.2})
    with pytest.raises(KeyError):
        await writer.freeze_config("missing", "fit", {})


async def test_record_input_is_idempotent_and_stores_truth(env):
    conn, writer = env
    await writer.record_input("i1", {"state": {"bars": [1.0]}}, "HIGH")
    await writer.record_input("i1", {"state": {"bars": [9.0]}}, "LOW")
    rows = conn.execute("SELECT task_type, ground_truth FROM inputs").fetchall()
    assert rows == [("high_low", "HIGH")]


async def test_record_decision_and_mark_used(env):
    conn, writer = env
    await writer.record_decision(
        experiment_id="e1",
        input_id="i1",
        aggregate_score=0.7,
        final_confidence=0.7,
        final_decision="HIGH",
        is_correct=1,
        total_latency=0.5,
        early_stopped=0,
    )
    rows = conn.execute("SELECT final_decision, is_correct FROM decisions").fetchall()
    assert rows == [("HIGH", 1)]

    insert_judge_log(conn, "e1", "i1", "hl_judge#0", 0.7)
    insert_judge_log(conn, "e1", "i1", "hl_judge#1", 0.6)
    await writer.mark_used("e1", "i1", ["hl_judge#0"], True)
    used = dict(conn.execute("SELECT judge_id, was_used FROM judge_logs").fetchall())
    assert used["hl_judge#0"] == 1 and used["hl_judge#1"] is None
```

```python
# tests/test_storage/test_reader.py
"""Reader helpers (spec §8, §9.1)."""

import math

import pytest
from helpers_exp1 import insert_call, insert_judge_log

from src.storage import db
from src.storage.reader import (
    CallRow,
    completed_units,
    completion_latency,
    load_calls,
    load_probabilities,
    pending_interpretations,
)


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "t.db")


def test_completed_units_include_error_calls(conn):
    insert_call(conn, "e1", "i1", 0)
    insert_call(conn, "e1", "i2", 1, status="error")
    insert_call(conn, "other", "i9", 0)
    assert completed_units(conn, "e1") == {("i1", 0), ("i2", 1)}


def test_load_probabilities_skips_errors_missing_and_out_of_range(conn):
    insert_judge_log(conn, "e1", "i1", "hl_judge#0", value=0.7)
    insert_judge_log(conn, "e1", "i1", "hl_judge#1", error="boom")
    insert_judge_log(conn, "e1", "i1", "hl_judge#2", value=None)
    insert_judge_log(conn, "e1", "i1", "hl_judge#3", value=1.5)
    insert_judge_log(conn, "e1", "i1", "hl_judge#4", value=math.nan)
    assert load_probabilities(conn, "e1") == {"i1": {"hl_judge#0": 0.7}}


def test_pending_interpretations_returns_uninterpreted_rows_only(conn):
    insert_judge_log(conn, "e1", "i1", "hl_judge#0", value=None, raw_p=0.8)
    insert_judge_log(conn, "e1", "i1", "hl_judge#1", value=0.7)
    insert_judge_log(conn, "e1", "i1", "hl_judge#2", error="x")
    pending = pending_interpretations(conn, "e1")
    assert [(c, j) for c, j, _ in pending] == [("c1", "hl_judge#0")]
    assert pending[0][2].raw_probability == 0.8


def test_load_calls_and_completion_latency(conn):
    insert_call(conn, "e1", "i1", 0, latency=0.25, usage={"input_tokens": 4})
    insert_call(conn, "e1", "i1", 1, latency=0.5)
    calls = load_calls(conn, "e1")
    assert isinstance(calls[0], CallRow)
    assert completion_latency(calls) == {"i1": 0.75}
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_storage -v`
Expected: FAIL (missing methods / module).

- [ ] **Step 3: Implement**

Append to `SqliteStorageWriter` in `src/storage/writer.py` (add `from typing import Any` to the imports):

```python
    async def record_experiment(
        self,
        experiment_id: str,
        config: dict[str, Any],
        aggregator_version: str | None = None,
    ) -> None:
        """Create the experiment row; a no-op when it already exists, so
        resumed runs keep the original configuration."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT OR IGNORE INTO experiments"
                    " (experiment_id, config_json, aggregator_version, created_at)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        experiment_id,
                        json.dumps(config, sort_keys=True),
                        aggregator_version,
                        now,
                    ),
                )

    async def freeze_config(self, experiment_id: str, key: str, value: Any) -> None:
        """Write `value` under `config_json["frozen"][key]`; never overwrite."""
        async with self._lock:
            with self._conn:
                row = self._conn.execute(
                    "SELECT config_json FROM experiments WHERE experiment_id = ?",
                    (experiment_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(experiment_id)
                config = json.loads(row[0])
                frozen = config.setdefault("frozen", {})
                if key in frozen:
                    raise ValueError(f"{key!r} already frozen for {experiment_id}")
                frozen[key] = value
                self._conn.execute(
                    "UPDATE experiments SET config_json = ? WHERE experiment_id = ?",
                    (json.dumps(config, sort_keys=True), experiment_id),
                )

    async def record_input(
        self,
        input_id: str,
        features: dict[str, Any],
        ground_truth: str | None,
        task_type: str = "high_low",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT OR IGNORE INTO inputs"
                    " (input_id, task_type, input_features_json, ground_truth,"
                    " created_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        input_id,
                        task_type,
                        json.dumps(features, sort_keys=True),
                        ground_truth,
                        now,
                    ),
                )

    async def record_decision(
        self,
        *,
        experiment_id: str,
        input_id: str,
        aggregate_score: float | None,
        final_confidence: float | None,
        final_decision: str | None,
        is_correct: int | None,
        total_latency: float | None,
        early_stopped: int | None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO decisions (experiment_id, input_id,"
                    " aggregate_score, final_confidence, final_decision, is_correct,"
                    " total_latency, early_stopped, timestamp)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        experiment_id,
                        input_id,
                        aggregate_score,
                        final_confidence,
                        final_decision,
                        is_correct,
                        total_latency,
                        early_stopped,
                        now,
                    ),
                )

    async def mark_used(
        self, experiment_id: str, input_id: str, judge_ids: list[str], used: bool
    ) -> None:
        """Set `was_used` for the named judges of one input (spec §8)."""
        if not judge_ids:
            return
        placeholders = ",".join("?" for _ in judge_ids)
        async with self._lock:
            with self._conn:
                self._conn.execute(
                    "UPDATE judge_logs SET was_used = ? WHERE experiment_id = ?"
                    f" AND input_id = ? AND judge_id IN ({placeholders})",
                    (int(used), experiment_id, input_id, *judge_ids),
                )
```

```python
# src/storage/reader.py
"""Read helpers over the Experiment 1 sqlite tables (spec §8, §9.1)."""

from __future__ import annotations

import json
import sqlite3

from pydantic import BaseModel

from src.judges.interface import Answer


class CallRow(BaseModel):
    input_id: str
    stage_index: int
    latency: float
    status: str
    token_usage: dict | None = None


def completed_units(
    conn: sqlite3.Connection, experiment_id: str
) -> set[tuple[str, int]]:
    """(input_id, stage_index) pairs with a recorded call, success or error."""
    rows = conn.execute(
        "SELECT input_id, stage_index FROM calls WHERE experiment_id = ?",
        (experiment_id,),
    )
    return {(input_id, stage) for input_id, stage in rows}


def load_probabilities(
    conn: sqlite3.Connection, experiment_id: str
) -> dict[str, dict[str, float]]:
    """input_id -> judge_id -> valid P(HIGH).

    Rows with an interpret error, a missing value, or a value outside
    [0, 1] (including NaN) are omitted, never repaired (spec §9).
    """
    out: dict[str, dict[str, float]] = {}
    rows = conn.execute(
        "SELECT input_id, judge_id, interpreted_value, interpret_error"
        " FROM judge_logs WHERE experiment_id = ?",
        (experiment_id,),
    )
    for input_id, judge_id, value, error in rows:
        if error is not None or value is None:
            continue
        try:
            p = float(value)
        except (TypeError, ValueError):
            continue
        if not 0.0 <= p <= 1.0:  # False for NaN as well
            continue
        out.setdefault(input_id, {})[judge_id] = p
    return out


def load_calls(conn: sqlite3.Connection, experiment_id: str) -> list[CallRow]:
    rows = conn.execute(
        "SELECT input_id, stage_index, latency, status, token_usage_json"
        " FROM calls WHERE experiment_id = ? ORDER BY input_id, stage_index",
        (experiment_id,),
    )
    return [
        CallRow(
            input_id=i,
            stage_index=s,
            latency=lat,
            status=st,
            token_usage=json.loads(usage) if usage else None,
        )
        for i, s, lat, st, usage in rows
    ]


def pending_interpretations(
    conn: sqlite3.Connection, experiment_id: str
) -> list[tuple[str, str, Answer]]:
    """Stored raw answers that have neither a value nor an interpret error."""
    rows = conn.execute(
        "SELECT call_id, judge_id, raw_answer_json FROM judge_logs"
        " WHERE experiment_id = ? AND interpreted_value IS NULL"
        " AND interpret_error IS NULL",
        (experiment_id,),
    )
    return [(c, j, Answer.model_validate_json(raw)) for c, j, raw in rows]


def completion_latency(calls: list[CallRow]) -> dict[str, float]:
    """Per-input ensemble completion time under sequential dispatch.

    The runner dispatches the replicas of one sample sequentially, so the
    completion time is the sum of that input's call latencies (spec §7).
    Never sum `judge_logs.judge_latency`: it repeats the request latency.
    """
    out: dict[str, float] = {}
    for call in calls:
        out[call.input_id] = out.get(call.input_id, 0.0) + call.latency
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_storage -v`
Expected: PASS. (If `tests/conftest.py` already exists, add the `sys.path` lines to it instead of overwriting.)

- [ ] **Step 5: Commit**

```bash
venv/bin/black src tests && venv/bin/ruff check src tests
git add src/storage tests
git commit -m "feat: 実験用のwriter拡張とstorage readerを追加する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Config and resumable runner

**Files:**
- Create: `src/experiments/__init__.py` (empty), `src/experiments/config.py`, `src/experiments/runner.py`
- Test: `tests/test_experiments/test_runner.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 4, 5.
- Produces: `Exp1Config` (with `target_key(target)`), `Pricing`; `ArmSpec(study_id, arm, topology, run, n_replicas, horizon)` with `.experiment_id` and `.units() -> list[tuple[int, list[HighLowJudge]]]`; `run_arm(spec, samples, executor, writer, conn, *, config_extra=None, sample_concurrency=1, max_units=None) -> int` (units executed); `finish_pending_interpretations(conn, writer, spec)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_experiments/test_runner.py
"""Runner topologies, resumability and failure handling (spec §5.3, §9)."""

import pytest
import typesafe_sdk as ts

from src.data.synthetic import SyntheticConfig, SyntheticSource
from src.experiments.runner import ArmSpec, finish_pending_interpretations, run_arm
from src.judges.interface import Answer, CallRecord, Question, RawJudgeRecord
from src.judges.jev_executor import JevStageExecutor
from src.storage import db
from src.storage.writer import SqliteStorageWriter


class FakeJevClient:
    def __init__(self, p=0.7, fail=False, drop=()):
        self.p, self.fail, self.drop = p, fail, set(drop)
        self.requests: list[list[str]] = []

    async def system_one(self, *, state, questions, **kwargs):
        self.requests.append(list(questions))
        if self.fail:
            raise ts.TypeSafeError("boom")
        return ts.SystemOneResponse(
            model="jev-test",
            usage=ts.Usage(input_tokens=10, output_tokens=2),
            answers={
                name: ts.NoulAnswer(noul=self.p)
                for name in questions
                if name not in self.drop
            },
        )


@pytest.fixture
def samples():
    cfg = SyntheticConfig(
        seed=5,
        split_sizes={"pilot": 4, "calib": 4, "thresh": 4, "test": 4, "test_shift": 4},
    )
    return SyntheticSource(cfg).samples("pilot")[:3]


@pytest.fixture
def env(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    return conn, SqliteStorageWriter(conn)


def _count(conn, sql, *params) -> int:
    return conn.execute(sql, params).fetchone()[0]


def test_experiment_ids_are_distinct_per_arm():
    ids = {
        ArmSpec(study_id="s", arm="A", run=1).experiment_id,
        ArmSpec(study_id="s", arm="A", run=2).experiment_id,
        ArmSpec(study_id="s", arm="C", topology="batched").experiment_id,
        ArmSpec(study_id="s", arm="C", topology="separate").experiment_id,
    }
    assert ids == {"s-A-run1", "s-A-run2", "s-C-batched", "s-C-separate"}


async def test_arm_a_makes_one_call_per_sample(env, samples):
    conn, writer = env
    client = FakeJevClient()
    spec = ArmSpec(study_id="s", arm="A", horizon=5)
    n = await run_arm(spec, samples, JevStageExecutor(client, writer), writer, conn)
    assert n == 3
    assert _count(conn, "SELECT COUNT(*) FROM calls WHERE experiment_id='s-A-run1'") == 3
    assert _count(conn, "SELECT COUNT(*) FROM judge_logs") == 3
    assert _count(conn, "SELECT COUNT(*) FROM inputs") == 3
    assert _count(conn, "SELECT COUNT(*) FROM experiments") == 1


async def test_arm_c_batched_sends_all_replicas_in_one_call(env, samples):
    conn, writer = env
    client = FakeJevClient()
    spec = ArmSpec(study_id="s", arm="C", topology="batched", n_replicas=5, horizon=5)
    await run_arm(spec, samples, JevStageExecutor(client, writer), writer, conn)
    assert _count(conn, "SELECT COUNT(*) FROM calls") == 3
    assert _count(conn, "SELECT COUNT(*) FROM judge_logs") == 15
    assert client.requests[0] == [f"hl_judge#{k}" for k in range(5)]


async def test_arm_c_separate_makes_one_call_per_replica(env, samples):
    conn, writer = env
    client = FakeJevClient()
    spec = ArmSpec(study_id="s", arm="C", topology="separate", n_replicas=5, horizon=5)
    await run_arm(spec, samples, JevStageExecutor(client, writer), writer, conn)
    assert _count(conn, "SELECT COUNT(*) FROM calls") == 15
    stages = {r[0] for r in conn.execute("SELECT DISTINCT stage_index FROM calls")}
    assert stages == {0, 1, 2, 3, 4}


async def test_rerun_executes_nothing_and_max_units_caps_new_work(env, samples):
    conn, writer = env
    executor = JevStageExecutor(FakeJevClient(), writer)
    spec = ArmSpec(study_id="s", arm="C", topology="separate", n_replicas=5, horizon=5)
    assert await run_arm(spec, samples, executor, writer, conn, max_units=4) == 4
    assert await run_arm(spec, samples, executor, writer, conn) == 11
    assert await run_arm(spec, samples, executor, writer, conn) == 0
    assert _count(conn, "SELECT COUNT(*) FROM calls") == 15


async def test_failed_calls_are_terminal_and_not_retried(env, samples):
    conn, writer = env
    executor = JevStageExecutor(FakeJevClient(fail=True), writer)
    spec = ArmSpec(study_id="s", arm="A", horizon=5)
    assert await run_arm(spec, samples, executor, writer, conn) == 3
    assert _count(conn, "SELECT COUNT(*) FROM calls WHERE status='error'") == 3
    assert _count(conn, "SELECT COUNT(*) FROM judge_logs") == 0
    assert await run_arm(spec, samples, executor, writer, conn) == 0


async def test_dropped_answer_leaves_a_missing_replica_row(env, samples):
    conn, writer = env
    client = FakeJevClient(drop={"hl_judge#2"})
    spec = ArmSpec(study_id="s", arm="C", topology="batched", n_replicas=5, horizon=5)
    await run_arm(spec, samples, JevStageExecutor(client, writer), writer, conn)
    assert _count(conn, "SELECT COUNT(*) FROM judge_logs") == 12  # 3 x 4


async def test_pending_interpretations_are_finished_without_new_calls(env):
    conn, writer = env
    call = CallRecord(
        call_id="c1",
        experiment_id="s-A-run1",
        input_id="i1",
        stage_index=0,
        executor="JevStageExecutor",
        question_count=1,
        latency=0.1,
        status="success",
    )
    raw = RawJudgeRecord(
        judge_id="hl_judge",
        judge_version="highlow-1.0",
        judge_prompt_or_definition="d",
        question=Question(kind="noul", prompt="p"),
        raw_answer=Answer(kind="noul", raw_value=0.8, raw_probability=0.8),
        latency=0.1,
    )
    await writer.record_call(call, [raw])
    spec = ArmSpec(study_id="s", arm="A", horizon=5)
    await finish_pending_interpretations(conn, writer, spec)
    value = conn.execute("SELECT interpreted_value FROM judge_logs").fetchone()[0]
    assert value == 0.8
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_experiments/test_runner.py -v`
Expected: FAIL (`ModuleNotFoundError: src.experiments.runner`).

- [ ] **Step 3: Implement**

```python
# src/experiments/__init__.py  (empty file)
```

```python
# src/experiments/config.py
"""Experiment 1 configuration (recorded into `experiments.config_json`)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.data.synthetic import SyntheticConfig


class Pricing(BaseModel):
    """USD per million tokens; provenance is kept next to the values."""

    input_per_mtok: float
    output_per_mtok: float
    source: str = ""


class Exp1Config(BaseModel):
    study_id: str = "exp1"
    db_path: str = "workspace/exp1.db"
    data: SyntheticConfig = Field(default_factory=SyntheticConfig)
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
    def _headline_is_a_target(self) -> Exp1Config:
        if self.headline_coverage not in self.coverage_targets:
            raise ValueError("headline_coverage must be one of coverage_targets")
        return self

    @staticmethod
    def target_key(target: float) -> str:
        """Stable string key for a coverage target."""
        return f"{target:.2f}"
```

```python
# src/experiments/runner.py
"""Resumable arm runner for A and C (spec §5.3, §9.1)."""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Any, Literal

from pydantic import BaseModel

from src.data.schema import Sample
from src.judges.definitions.high_low import HighLowJudge, replica_index
from src.judges.interface import JudgeExecutor
from src.storage.reader import completed_units, pending_interpretations
from src.storage.writer import SqliteStorageWriter


class ArmSpec(BaseModel):
    study_id: str
    arm: Literal["A", "C"]
    topology: Literal["batched", "separate"] = "batched"
    run: int = 1
    n_replicas: int = 5
    horizon: int = 5

    @property
    def experiment_id(self) -> str:
        if self.arm == "A":
            return f"{self.study_id}-A-run{self.run}"
        return f"{self.study_id}-C-{self.topology}"

    def units(self) -> list[tuple[int, list[HighLowJudge]]]:
        """(stage_index, judges) execution units for one sample."""
        if self.arm == "A":
            return [(0, [HighLowJudge(self.horizon)])]
        replicas = [HighLowJudge(self.horizon, k) for k in range(self.n_replicas)]
        if self.topology == "batched":
            return [(0, replicas)]
        return [(k, [judge]) for k, judge in enumerate(replicas)]


class _Budget:
    def __init__(self, limit: int | None) -> None:
        self._limit = limit
        self.used = 0

    def take(self) -> bool:
        if self._limit is not None and self.used >= self._limit:
            return False
        self.used += 1
        return True


async def finish_pending_interpretations(
    conn: sqlite3.Connection, writer: SqliteStorageWriter, spec: ArmSpec
) -> None:
    """Re-interpret stored raw answers left without a result (no API call)."""
    for call_id, judge_id, answer in pending_interpretations(conn, spec.experiment_id):
        judge = HighLowJudge(spec.horizon, replica_index(judge_id))
        try:
            decision = judge.interpret(answer)
        except Exception as exc:  # noqa: BLE001 - recorded, never re-raised
            await writer.record_interpretation(call_id, judge_id, None, str(exc))
            continue
        await writer.record_interpretation(call_id, judge_id, decision, None)


async def run_arm(
    spec: ArmSpec,
    samples: list[Sample],
    executor: JudgeExecutor,
    writer: SqliteStorageWriter,
    conn: sqlite3.Connection,
    *,
    config_extra: dict[str, Any] | None = None,
    sample_concurrency: int = 1,
    max_units: int | None = None,
) -> int:
    """Run every incomplete unit of `spec` over `samples`; return units run.

    A unit is complete when a call for `(input_id, stage_index)` is stored,
    whatever its status; failed calls and dropped answers are never retried
    (spec §9.1). Replicas of one sample run sequentially, so completion
    time is the sum of call latencies.
    """
    config = {
        **spec.model_dump(),
        "dispatch": {
            "sample_concurrency": sample_concurrency,
            "replica_dispatch": "sequential",
        },
        **(config_extra or {}),
    }
    await writer.record_experiment(spec.experiment_id, config)
    await finish_pending_interpretations(conn, writer, spec)
    done = completed_units(conn, spec.experiment_id)
    budget = _Budget(max_units)
    semaphore = asyncio.Semaphore(sample_concurrency)

    async def run_sample(sample: Sample) -> None:
        async with semaphore:
            await writer.record_input(
                sample.input_id,
                {
                    "state": sample.state,
                    "regime": sample.regime,
                    "split": sample.split,
                    "t_index": sample.t_index,
                },
                sample.label,
            )
            for stage_index, judges in spec.units():
                if (sample.input_id, stage_index) in done:
                    continue
                if not budget.take():
                    return
                await executor.run_stage(
                    sample.state,
                    judges,
                    experiment_id=spec.experiment_id,
                    input_id=sample.input_id,
                    stage_index=stage_index,
                )

    await asyncio.gather(*(run_sample(s) for s in samples))
    return budget.used
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_experiments -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
venv/bin/black src tests && venv/bin/ruff check src tests
git add src/experiments tests/test_experiments
git commit -m "feat: A/Cの再開可能なrunnerとExp1Configを追加する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Pilot statistics and CLI

**Files:**
- Create: `src/experiments/pilot.py`, `src/experiments/cli.py`, `configs/exp1.example.json`
- Modify: `.gitignore` (add `workspace/`, `*.db`, `*.db-wal`, `*.db-shm`)
- Test: `tests/test_experiments/test_pilot.py`

**Interfaces:**
- Produces: `PilotStats`, `pilot_stats(probs_by_input, labels) -> PilotStats`, `collect_replica_probs(conn, experiment_ids) -> dict[str, list[float]]`, constants `NEGLIGIBLE_MEAN_STD = 0.01`, `NEGLIGIBLE_DISAGREEMENT = 0.02` (predeclared before any pilot data exists, spec §5.4); CLI commands `run`, `pilot-stats` (the `report` command is added in Task 11).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_experiments/test_pilot.py
"""Pilot variance statistics (spec §5.4)."""

from pathlib import Path

import pytest
from helpers_exp1 import insert_judge_log

from src.experiments.config import Exp1Config
from src.experiments.pilot import collect_replica_probs, pilot_stats
from src.storage import db

LABELS = {"i1": "HIGH", "i2": "LOW", "i3": "HIGH"}


def test_identical_replicas_are_negligible_and_correlation_is_none():
    probs = {i: [0.7, 0.7, 0.7] for i in LABELS}
    stats = pilot_stats(probs, LABELS)
    assert stats.mean_std == 0.0
    assert stats.disagreement_rate == 0.0
    assert stats.error_correlation is None  # zero variance in every pair
    assert stats.negligible is True


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
    insert_judge_log(conn, "A1", "i1", "hl_judge", value=0.6)
    insert_judge_log(conn, "A2", "i1", "hl_judge", value=0.8)
    insert_judge_log(conn, "A1", "i2", "hl_judge", value=0.4)  # missing in A2
    assert collect_replica_probs(conn, ["A1", "A2"]) == {"i1": [0.6, 0.8]}


def test_example_config_loads():
    text = Path("configs/exp1.example.json").read_text()
    cfg = Exp1Config.model_validate_json(text)
    assert cfg.n_replicas == 5 and cfg.headline_coverage in cfg.coverage_targets
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_experiments/test_pilot.py -v`
Expected: FAIL (`ModuleNotFoundError: src.experiments.pilot`).

- [ ] **Step 3: Implement**

```python
# src/experiments/pilot.py
"""Replica-variance statistics that gate the N/topology choice (spec §5.4).

The negligible-variance thresholds below were fixed before any pilot data
existed; do not tune them after looking at results.
"""

from __future__ import annotations

import itertools
import sqlite3
import statistics

from pydantic import BaseModel

from src.data.schema import Label
from src.storage.reader import load_probabilities

NEGLIGIBLE_MEAN_STD = 0.01
NEGLIGIBLE_DISAGREEMENT = 0.02


class PilotStats(BaseModel):
    n_inputs: int
    mean_std: float  # mean over inputs of the std across replicas
    disagreement_rate: float  # share of inputs whose replicas straddle 0.5
    error_correlation: float | None  # mean pairwise correlation of errors
    negligible: bool


def pilot_stats(
    probs_by_input: dict[str, list[float]], labels: dict[str, Label]
) -> PilotStats:
    rows = {i: v for i, v in probs_by_input.items() if len(v) >= 2 and i in labels}
    if not rows:
        raise ValueError("no inputs with at least two replicas")
    mean_std = statistics.fmean(statistics.pstdev(v) for v in rows.values())
    disagreement = statistics.fmean(
        float(len({p > 0.5 for p in v}) > 1) for v in rows.values()
    )
    n_replicas = min(len(v) for v in rows.values())
    errors = [
        [float((v[k] > 0.5) != (labels[i] == "HIGH")) for i, v in rows.items()]
        for k in range(n_replicas)
    ]
    corrs: list[float] = []
    for a, b in itertools.combinations(errors, 2):
        try:
            corrs.append(statistics.correlation(a, b))
        except statistics.StatisticsError:  # a constant series has no correlation
            continue
    return PilotStats(
        n_inputs=len(rows),
        mean_std=mean_std,
        disagreement_rate=disagreement,
        error_correlation=statistics.fmean(corrs) if corrs else None,
        negligible=mean_std < NEGLIGIBLE_MEAN_STD
        and disagreement < NEGLIGIBLE_DISAGREEMENT,
    )


def collect_replica_probs(
    conn: sqlite3.Connection, experiment_ids: list[str]
) -> dict[str, list[float]]:
    """Stack valid P(HIGH) per input across experiments.

    Passing `[A-run1, A-run2]` compares two repeat runs; passing
    `[C-batched]` compares its N replicas. Only inputs present in every
    experiment are kept.
    """
    per_experiment = [load_probabilities(conn, e) for e in experiment_ids]
    common = set.intersection(*(set(p) for p in per_experiment))
    return {
        i: [v for p in per_experiment for _, v in sorted(p[i].items())] for i in common
    }
```

`configs/exp1.example.json`:

```json
{
  "study_id": "exp1",
  "db_path": "workspace/exp1.db",
  "n_replicas": 5,
  "model": null,
  "extra_body": null,
  "pricing": null,
  "data": {
    "seed": 0,
    "window": 60,
    "horizon": 5,
    "stride": 5,
    "split_sizes": {"pilot": 30, "calib": 200, "thresh": 200, "test": 300, "test_shift": 300}
  },
  "coverage_targets": [1.0, 0.8, 0.6],
  "headline_coverage": 0.8
}
```

`.gitignore`: append the lines `workspace/`, `*.db`, `*.db-wal`, `*.db-shm`.

The CLI builds the SDK client without passing any credential: the SDK reads it from the environment, and `Settings.load()` is called first purely to fail fast with a clear error when it is missing (`src/config.py` also loads the local environment file).

```python
# src/experiments/cli.py
"""Thin command-line entry points: run, pilot-stats, report.

`run` calls the real Jev API and spends money; it is human-only (Task 13).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import typesafe_sdk as ts

from src.config import Settings
from src.data.schema import SPLITS
from src.data.synthetic import SyntheticSource
from src.experiments.config import Exp1Config
from src.experiments.pilot import collect_replica_probs, pilot_stats
from src.experiments.runner import ArmSpec, run_arm
from src.judges.jev_executor import JevStageExecutor
from src.storage import db
from src.storage.writer import SqliteStorageWriter


def _load(path: str) -> Exp1Config:
    return Exp1Config.model_validate_json(Path(path).read_text())


async def _run(args: argparse.Namespace) -> None:
    cfg = _load(args.config)
    source = SyntheticSource(cfg.data)
    spec = ArmSpec(
        study_id=cfg.study_id,
        arm=args.arm,
        topology=args.topology,
        run=args.run,
        n_replicas=cfg.n_replicas,
        horizon=cfg.data.horizon,
    )
    Path(cfg.db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(cfg.db_path)
    writer = SqliteStorageWriter(conn)
    extra = {
        "data": cfg.data.model_dump(),
        "excluded": source.data.excluded,
        "requested_model": cfg.model,
        "extra_body": cfg.extra_body,
        "pricing": cfg.pricing.model_dump() if cfg.pricing else None,
    }
    Settings.load()  # fail fast if the credential is missing; value unused
    async with ts.AsyncTypeSafeClient() as client:  # SDK reads it from the environment
        executor = JevStageExecutor(
            client, writer, model=cfg.model, extra_body=cfg.extra_body
        )
        used = await run_arm(
            spec,
            source.samples(args.split),
            executor,
            writer,
            conn,
            config_extra=extra,
            sample_concurrency=cfg.sample_concurrency,
            max_units=args.max_units,
        )
    print(f"{spec.experiment_id}: executed {used} units")


def _pilot_stats(args: argparse.Namespace) -> None:
    cfg = _load(args.config)
    source = SyntheticSource(cfg.data)
    labels = {s.input_id: s.label for s in source.samples("pilot")}
    conn = db.connect(cfg.db_path)
    stats = pilot_stats(collect_replica_probs(conn, args.experiments), labels)
    print(json.dumps(stats.model_dump(), indent=2))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="exp1")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one arm over one split (spends API budget)")
    run.add_argument("--config", required=True)
    run.add_argument("--arm", choices=["A", "C"], required=True)
    run.add_argument("--topology", choices=["batched", "separate"], default="batched")
    run.add_argument("--run", type=int, default=1)
    run.add_argument("--split", choices=list(SPLITS), required=True)
    run.add_argument("--max-units", type=int, default=None)

    ps = sub.add_parser("pilot-stats", help="replica variance for stored experiments")
    ps.add_argument("--config", required=True)
    ps.add_argument("--experiments", nargs="+", required=True)

    args = parser.parse_args(argv)
    if args.command == "run":
        asyncio.run(_run(args))
    elif args.command == "pilot-stats":
        _pilot_stats(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_experiments -v && venv/bin/python -m src.experiments.cli --help`
Expected: tests PASS; help lists `run` and `pilot-stats`. (Do not run the `run` command: it spends real budget.)

- [ ] **Step 5: Commit**

```bash
venv/bin/black src tests && venv/bin/ruff check src tests
git add src/experiments configs/exp1.example.json .gitignore tests
git commit -m "feat: pilot統計・CLI・設定例を追加する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

**GATE after Task 7:** the real-API pilot (Task 13, step 2) is human-run. Tasks 8-12 are offline and do not depend on its outcome; the pilot decides only N, topology, split sizes, and whether the §5.4 fallback discussion is needed.

---

### Task 8: Aggregation core

**Files:**
- Create: `src/aggregation/__init__.py` (empty), `src/aggregation/core.py`
- Test: `tests/test_aggregation/test_core.py`

**Interfaces:**
- Produces: `mean_probability(values, n_expected) -> float | None`; `IsotonicCalibrator.fit(ps, ys)`, `.predict(p)`, `.to_dict()`, `.from_dict(d)`; `decide(p, m) -> "HIGH"|"LOW"|"SKIP"`; `margin_grid(step) -> list[float]`; `MarginChoice(margin, achieved, reached)`; `choose_margin(ps, target, grid) -> MarginChoice`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_aggregation/test_core.py
"""Aggregation rules (spec §6)."""

import pytest

from src.aggregation.core import (
    IsotonicCalibrator,
    choose_margin,
    decide,
    margin_grid,
    mean_probability,
)


def test_mean_requires_exactly_n_valid_values():
    assert mean_probability([0.2, 0.4], 2) == pytest.approx(0.3)
    assert mean_probability([0.2], 2) is None  # survivors are never averaged
    assert mean_probability([], 5) is None


def test_decide_boundaries_and_exact_half_is_skip():
    assert decide(0.75, 0.25) == "HIGH"  # inclusive for m > 0
    assert decide(0.25, 0.25) == "LOW"
    assert decide(0.5, 0.0) == "SKIP"  # branches must not both fire at m = 0
    assert decide(0.5000001, 0.0) == "HIGH"
    assert decide(0.4999999, 0.0) == "LOW"
    assert decide(0.6, 0.25) == "SKIP"


def test_isotonic_pools_violations_and_clamps():
    cal = IsotonicCalibrator.fit([0.1, 0.2, 0.3, 0.4], [0, 1, 0, 1])
    assert cal.predict(0.1) == 0.0
    assert cal.predict(0.3) == 0.5  # pooled with 0.2
    assert cal.predict(0.4) == 1.0
    assert cal.predict(0.05) == 0.0  # below range: clamped
    assert cal.predict(0.9) == 1.0  # above range: clamped


def test_isotonic_pools_equal_inputs_and_handles_constant_data():
    assert IsotonicCalibrator.fit([0.5, 0.5], [0, 1]).predict(0.5) == 0.5
    constant = IsotonicCalibrator.fit([0.7, 0.7, 0.7], [1, 1, 0])
    assert constant.predict(0.1) == constant.predict(0.9) == pytest.approx(2 / 3)


def test_isotonic_roundtrip_and_empty_fit():
    cal = IsotonicCalibrator.fit([0.1, 0.5, 0.9], [0, 1, 1])
    again = IsotonicCalibrator.from_dict(cal.to_dict())
    probes = (0.0, 0.5, 1.0)
    assert [again.predict(p) for p in probes] == [cal.predict(p) for p in probes]
    with pytest.raises(ValueError):
        IsotonicCalibrator.fit([], [])


def test_choose_margin_takes_largest_margin_meeting_target():
    ps = [0.95, 0.75, 0.5, 0.25, 0.05]
    grid = [0.0, 0.1, 0.2, 0.3, 0.4]
    assert choose_margin(ps, 0.8, grid).margin == 0.2
    assert choose_margin(ps, 0.4, grid).margin == 0.4
    unreachable = choose_margin(ps, 1.0, grid)  # p = 0.5 is always SKIP
    assert (unreachable.margin, unreachable.achieved, unreachable.reached) == (
        0.0,
        0.8,
        False,
    )


def test_choose_margin_rejects_empty_input_and_margin_grid_spans_half():
    with pytest.raises(ValueError):
        choose_margin([], 0.8, [0.0])
    grid = margin_grid(0.1)
    assert grid[0] == 0.0 and grid[-1] == 0.5 and len(grid) == 6
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_aggregation -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# src/aggregation/__init__.py  (empty file)
```

```python
# src/aggregation/core.py
"""Mean, isotonic calibration, decision rule and margin selection (spec §6).

Isotonic regression is the standard pool-adjacent-violators algorithm,
implemented here directly (no new dependency).
"""

from __future__ import annotations

from bisect import bisect_right
from typing import Literal

from pydantic import BaseModel

Decision = Literal["HIGH", "LOW", "SKIP"]


def mean_probability(values: list[float], n_expected: int) -> float | None:
    """Mean of exactly `n_expected` valid values, else None (invalid sample)."""
    if len(values) != n_expected:
        return None
    return sum(values) / n_expected


class IsotonicCalibrator:
    """Non-decreasing step function fitted by pooling adjacent violators."""

    def __init__(self, xs: list[float], values: list[float]) -> None:
        self._xs = xs  # lower bound of each pooled block, ascending
        self._values = values

    @classmethod
    def fit(cls, ps: list[float], ys: list[float]) -> IsotonicCalibrator:
        if not ps:
            raise ValueError("cannot fit a calibrator on no data")
        grouped: dict[float, list[float]] = {}
        for p, y in zip(ps, ys):
            cell = grouped.setdefault(p, [0.0, 0.0])
            cell[0] += 1.0
            cell[1] += y
        blocks: list[list[float]] = []  # [x_lo, weight, sum_y]
        for x in sorted(grouped):
            weight, total = grouped[x]
            blocks.append([x, weight, total])
            while (
                len(blocks) >= 2
                and blocks[-2][2] / blocks[-2][1] > blocks[-1][2] / blocks[-1][1]
            ):
                _, weight2, total2 = blocks.pop()
                blocks[-1][1] += weight2
                blocks[-1][2] += total2
        return cls([b[0] for b in blocks], [b[2] / b[1] for b in blocks])

    def predict(self, p: float) -> float:
        # Clamp instead of extrapolating outside the fitted range.
        index = max(bisect_right(self._xs, p) - 1, 0)
        return self._values[index]

    def to_dict(self) -> dict[str, list[float]]:
        return {"xs": list(self._xs), "values": list(self._values)}

    @classmethod
    def from_dict(cls, data: dict[str, list[float]]) -> IsotonicCalibrator:
        return cls(list(data["xs"]), list(data["values"]))


def decide(p: float, m: float) -> Decision:
    """HIGH/LOW/SKIP for calibrated probability `p` and margin `m >= 0`.

    Inclusive at the margin boundary for m > 0; exactly p = 0.5 is always
    SKIP so the two branches are mutually exclusive at m = 0.
    """
    if p > 0.5 and p >= 0.5 + m:
        return "HIGH"
    if p < 0.5 and p <= 0.5 - m:
        return "LOW"
    return "SKIP"


def margin_grid(step: float) -> list[float]:
    """Ascending margins 0, step, 2*step, ... up to 0.5."""
    return [round(i * step, 10) for i in range(int(round(0.5 / step)) + 1)]


class MarginChoice(BaseModel):
    margin: float
    achieved: float  # coverage over the valid thresh samples
    reached: bool  # False when the target is unattainable (spec §6.4)


def _coverage(ps: list[float], m: float) -> float:
    return sum(decide(p, m) != "SKIP" for p in ps) / len(ps)


def choose_margin(ps: list[float], target: float, grid: list[float]) -> MarginChoice:
    """Largest grid margin whose coverage is at least `target`.

    Coverage is non-increasing in the margin, so scan from the top. When
    even the smallest margin falls short (p = 0.5 plateaus), return it
    with `reached=False`.
    """
    if not ps:
        raise ValueError("no thresh samples to choose a margin from")
    for m in sorted(grid, reverse=True):
        coverage = _coverage(ps, m)
        if coverage + 1e-12 >= target:
            return MarginChoice(margin=m, achieved=coverage, reached=True)
    smallest = min(grid)
    return MarginChoice(
        margin=smallest, achieved=_coverage(ps, smallest), reached=False
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_aggregation -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
venv/bin/black src tests && venv/bin/ruff check src tests
git add src/aggregation tests/test_aggregation
git commit -m "feat: 平均・isotonic校正・マージン選択を追加する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Metrics core

**Files:**
- Create: `src/metrics/__init__.py` (empty), `src/metrics/core.py`
- Test: `tests/test_metrics/test_core.py`

**Interfaces:**
- Consumes: `decide` from Task 8.
- Produces: `Row(input_id, regime, label, t_index, p)` (`p` = calibrated P(HIGH) or `None` for an invalid sample); `AccCov`; `acted_accuracy_coverage(rows, margin) -> AccCov`; `brier(rows)`, `log_loss(rows, delta)` (both `None` without valid rows); `CurvePoint`; `risk_coverage(rows, grid)`; `accuracy_at_coverage(curve, level)`; `reliability(rows, bins=10)`; `percentile(values, q)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_metrics/test_core.py
"""Hand-computable metric tables (spec §7)."""

import math

import pytest

from src.metrics.core import (
    Row,
    accuracy_at_coverage,
    acted_accuracy_coverage,
    brier,
    log_loss,
    percentile,
    reliability,
    risk_coverage,
)


def _rows() -> list[Row]:
    spec = [(0.9, "HIGH"), (0.8, "LOW"), (0.2, "LOW"), (0.5, "HIGH"), (None, "HIGH")]
    return [
        Row(input_id=f"i{k}", regime="trend", label=label, t_index=k, p=p)
        for k, (p, label) in enumerate(spec)
    ]


def test_acted_accuracy_and_both_coverages():
    result = acted_accuracy_coverage(_rows(), 0.25)
    assert result.n_acted == 3 and result.n_valid == 4
    assert result.accuracy == pytest.approx(2 / 3)
    assert result.coverage_valid == pytest.approx(3 / 4)
    assert result.coverage_all == pytest.approx(3 / 5)  # invalid counts as not acted


def test_empty_acted_and_empty_valid_sets_give_none():
    all_skip = [r for r in _rows() if r.p == 0.5]
    assert acted_accuracy_coverage(all_skip, 0.0).accuracy is None
    assert acted_accuracy_coverage([], 0.1).coverage_valid is None
    invalid_only = [r for r in _rows() if r.p is None]
    assert acted_accuracy_coverage(invalid_only, 0.1).coverage_valid is None
    assert brier(invalid_only) is None and log_loss(invalid_only, 1e-6) is None


def test_brier_and_log_loss_over_valid_rows():
    assert brier(_rows()) == pytest.approx((0.01 + 0.64 + 0.04 + 0.25) / 4)
    expected = -(math.log(0.9) + math.log(0.2) + math.log(0.8) + math.log(0.5)) / 4
    assert log_loss(_rows(), 1e-6) == pytest.approx(expected)


def test_log_loss_clips_only_for_the_computation():
    rows = [Row(input_id="i", regime="r", label="LOW", t_index=0, p=1.0)]
    assert log_loss(rows, 1e-6) == pytest.approx(-math.log(1e-6))
    assert rows[0].p == 1.0


def test_risk_coverage_and_interpolation():
    curve = risk_coverage(_rows(), [0.0, 0.25, 0.39])
    assert [round(c.coverage, 4) for c in curve] == [0.75, 0.75, 0.25]
    assert curve[-1].accuracy == 1.0
    assert accuracy_at_coverage(curve, 0.5) == pytest.approx(1.0 - 0.5 * (1 / 3))
    assert accuracy_at_coverage(curve, 0.9) is None  # above the reachable range
    assert accuracy_at_coverage(curve, 0.1) is None  # below the reachable range


def test_reliability_bins_and_percentile():
    bins = reliability(_rows(), bins=2)
    assert [b["n"] for b in bins] == [1, 3]  # p<0.5 -> bin 0; 0.5,0.8,0.9 -> bin 1
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.95) == 4.0
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_metrics/test_core.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# src/metrics/__init__.py  (empty file)
```

```python
# src/metrics/core.py
"""Row-level metrics for one arm (spec §7). Pure functions, no I/O."""

from __future__ import annotations

import math

from pydantic import BaseModel

from src.aggregation.core import decide
from src.data.schema import Label


class Row(BaseModel):
    """One sample's result for one arm; `p` is None for an invalid sample."""

    input_id: str
    regime: str
    label: Label
    t_index: int
    p: float | None  # calibrated P(HIGH)


class AccCov(BaseModel):
    accuracy: float | None  # among acted samples
    coverage_valid: float | None  # acted / valid
    coverage_all: float  # acted / all labelled (invalid counts as not acted)
    n_valid: int
    n_acted: int


def acted_accuracy_coverage(rows: list[Row], margin: float) -> AccCov:
    valid = [r for r in rows if r.p is not None]
    decided = [(r, decide(r.p, margin)) for r in valid]
    acted = [(r, d) for r, d in decided if d != "SKIP"]
    correct = sum(d == r.label for r, d in acted)
    return AccCov(
        accuracy=correct / len(acted) if acted else None,
        coverage_valid=len(acted) / len(valid) if valid else None,
        coverage_all=len(acted) / len(rows) if rows else 0.0,
        n_valid=len(valid),
        n_acted=len(acted),
    )


def brier(rows: list[Row]) -> float | None:
    valid = [r for r in rows if r.p is not None]
    if not valid:
        return None
    return sum((r.p - (r.label == "HIGH")) ** 2 for r in valid) / len(valid)


def log_loss(rows: list[Row], delta: float) -> float | None:
    """Mean negative log-likelihood; probabilities are clipped to
    [delta, 1 - delta] for this computation only."""
    valid = [r for r in rows if r.p is not None]
    if not valid:
        return None
    total = 0.0
    for r in valid:
        p = min(max(r.p, delta), 1.0 - delta)
        total -= math.log(p if r.label == "HIGH" else 1.0 - p)
    return total / len(valid)


class CurvePoint(BaseModel):
    margin: float
    coverage: float  # acted / valid
    accuracy: float | None


def risk_coverage(rows: list[Row], grid: list[float]) -> list[CurvePoint]:
    points: list[CurvePoint] = []
    for m in grid:
        result = acted_accuracy_coverage(rows, m)
        if result.coverage_valid is None:
            continue
        points.append(
            CurvePoint(
                margin=m, coverage=result.coverage_valid, accuracy=result.accuracy
            )
        )
    return points


def accuracy_at_coverage(curve: list[CurvePoint], level: float) -> float | None:
    """Linear interpolation of accuracy at `level`; None outside the
    range the arm can reach (spec §6.6)."""
    points = sorted(
        (c for c in curve if c.accuracy is not None), key=lambda c: c.coverage
    )
    for lo, hi in zip(points, points[1:]):
        if lo.coverage <= level <= hi.coverage and hi.coverage > lo.coverage:
            t = (level - lo.coverage) / (hi.coverage - lo.coverage)
            return lo.accuracy + t * (hi.accuracy - lo.accuracy)
    for p in points:
        if abs(p.coverage - level) < 1e-12:
            return p.accuracy
    return None


def reliability(rows: list[Row], bins: int = 10) -> list[dict]:
    """Per-bin count, mean predicted P(HIGH) and observed HIGH frequency."""
    out = [{"bin": b, "n": 0, "sum_p": 0.0, "sum_high": 0.0} for b in range(bins)]
    for r in rows:
        if r.p is None:
            continue
        cell = out[min(int(r.p * bins), bins - 1)]
        cell["n"] += 1
        cell["sum_p"] += r.p
        cell["sum_high"] += r.label == "HIGH"
    return [
        {
            "bin": c["bin"],
            "n": c["n"],
            "mean_p": c["sum_p"] / c["n"] if c["n"] else None,
            "frac_high": c["sum_high"] / c["n"] if c["n"] else None,
        }
        for c in out
    ]


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile, q in (0, 1]."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_metrics -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
venv/bin/black src tests && venv/bin/ruff check src tests
git add src/metrics tests/test_metrics
git commit -m "feat: 行単位の指標・risk-coverage・補間を追加する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Paired block bootstrap, pipeline, and report

**Files:**
- Create: `src/metrics/bootstrap.py`, `src/experiments/pipeline.py`, `src/metrics/report.py`
- Test: `tests/test_metrics/test_bootstrap.py`, `tests/test_metrics/test_report.py`

**Interfaces:**
- Consumes: Tasks 5, 8, 9, 6 (`Exp1Config`).
- Produces:
  - `moving_block_resample(n, block_len, rng) -> list[int]`; `paired_block_ci(n, block_len, n_resamples, seed, stat, alpha=0.05) -> tuple[float, float] | None`.
  - `ArmFit(experiment_id, n_expected, calibrator, margins)`; `raw_means(conn, experiment_id, n_expected, samples) -> dict[str, float | None]`; `async fit_arm(conn, writer, experiment_id, n_expected, calib, thresh, cfg) -> ArmFit` (freezes the fit); `score_rows(conn, fit, samples) -> list[Row]`; `async write_decisions(conn, writer, fit, rows, margin)`.
  - `arm_cost(calls, pricing) -> dict`; `compare_arms(rows_a, rows_c, fit_a, fit_c, cfg, *, calls_a, calls_c, references=None) -> dict`; `render_markdown(report) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_metrics/test_bootstrap.py
"""Moving-block paired bootstrap (spec §7)."""

import random

from src.metrics.bootstrap import moving_block_resample, paired_block_ci


def test_resample_has_n_indices_in_range_and_is_seeded():
    a = moving_block_resample(10, 4, random.Random(0))
    b = moving_block_resample(10, 4, random.Random(0))
    assert a == b and len(a) == 10 and all(0 <= i < 10 for i in a)
    assert moving_block_resample(0, 4, random.Random(0)) == []


def test_blocks_are_contiguous_runs():
    idx = moving_block_resample(12, 4, random.Random(1))
    for start in (0, 4, 8):
        block = idx[start : start + 4]
        assert block == list(range(block[0], block[0] + 4))


def test_ci_brackets_a_constant_statistic_and_returns_none_when_undefined():
    ci = paired_block_ci(20, 5, 50, 0, lambda idx: 0.25)
    assert ci == (0.25, 0.25)
    assert paired_block_ci(20, 5, 50, 0, lambda idx: None) is None
```

```python
# tests/test_metrics/test_report.py
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
```

Pipeline functions are covered end-to-end in Task 11.

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/pytest tests/test_metrics -v`
Expected: FAIL (`ModuleNotFoundError: src.metrics.bootstrap`).

- [ ] **Step 3: Implement**

```python
# src/metrics/bootstrap.py
"""Moving-block paired bootstrap (spec §7).

Samples are time-ordered; contiguous blocks keep overlapping input
windows and persistent regimes together. Invalid-sample gaps are ignored:
the bootstrap runs over the time-ordered common valid samples.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable


def moving_block_resample(n: int, block_len: int, rng: random.Random) -> list[int]:
    """Indices of `n` items drawn as contiguous blocks of `block_len`."""
    if n == 0:
        return []
    indices: list[int] = []
    for _ in range(math.ceil(n / block_len)):
        start = rng.randrange(0, max(n - block_len, 0) + 1)
        indices.extend(range(start, min(start + block_len, n)))
    return indices[:n]


def paired_block_ci(
    n: int,
    block_len: int,
    n_resamples: int,
    seed: int,
    stat: Callable[[list[int]], float | None],
    alpha: float = 0.05,
) -> tuple[float, float] | None:
    """Percentile CI of `stat` over resampled index lists; None if `stat`
    is undefined for every resample. The same indices feed both arms
    because `stat` closes over paired data (paired resampling)."""
    rng = random.Random(seed)
    values = []
    for _ in range(n_resamples):
        v = stat(moving_block_resample(n, block_len, rng))
        if v is not None:
            values.append(v)
    if not values:
        return None
    values.sort()
    lo = values[int(alpha / 2 * len(values))]
    hi = values[min(len(values) - 1, int((1 - alpha / 2) * len(values)))]
    return lo, hi
```

```python
# src/experiments/pipeline.py
"""Offline fit / score / persist steps over stored raw answers (spec §6)."""

from __future__ import annotations

import sqlite3

from pydantic import BaseModel

from src.aggregation.core import (
    IsotonicCalibrator,
    MarginChoice,
    choose_margin,
    decide,
    margin_grid,
    mean_probability,
)
from src.data.schema import Sample
from src.experiments.config import Exp1Config
from src.metrics.core import Row
from src.storage.reader import completion_latency, load_calls, load_probabilities
from src.storage.writer import SqliteStorageWriter


class ArmFit(BaseModel):
    experiment_id: str
    n_expected: int
    calibrator: dict[str, list[float]]
    margins: dict[str, MarginChoice]  # keyed by Exp1Config.target_key


def raw_means(
    conn: sqlite3.Connection,
    experiment_id: str,
    n_expected: int,
    samples: list[Sample],
) -> dict[str, float | None]:
    """Mean P(HIGH) per sample; None when fewer than N valid answers."""
    probs = load_probabilities(conn, experiment_id)
    return {
        s.input_id: mean_probability(
            list(probs.get(s.input_id, {}).values()), n_expected
        )
        for s in samples
    }


async def fit_arm(
    conn: sqlite3.Connection,
    writer: SqliteStorageWriter,
    experiment_id: str,
    n_expected: int,
    calib: list[Sample],
    thresh: list[Sample],
    cfg: Exp1Config,
) -> ArmFit:
    """Fit the calibrator on `calib`, choose margins on `thresh`, freeze both."""
    means = raw_means(conn, experiment_id, n_expected, calib)
    pairs = [
        (means[s.input_id], 1.0 if s.label == "HIGH" else 0.0)
        for s in calib
        if means[s.input_id] is not None
    ]
    calibrator = IsotonicCalibrator.fit([p for p, _ in pairs], [y for _, y in pairs])
    thresh_means = raw_means(conn, experiment_id, n_expected, thresh)
    thresh_ps = [calibrator.predict(m) for m in thresh_means.values() if m is not None]
    grid = margin_grid(cfg.margin_step)
    fit = ArmFit(
        experiment_id=experiment_id,
        n_expected=n_expected,
        calibrator=calibrator.to_dict(),
        margins={
            cfg.target_key(t): choose_margin(thresh_ps, t, grid)
            for t in cfg.coverage_targets
        },
    )
    await writer.freeze_config(experiment_id, "fit", fit.model_dump())
    return fit


def score_rows(
    conn: sqlite3.Connection, fit: ArmFit, samples: list[Sample]
) -> list[Row]:
    """Apply the frozen calibrator; invalid samples keep `p = None`."""
    calibrator = IsotonicCalibrator.from_dict(fit.calibrator)
    means = raw_means(conn, fit.experiment_id, fit.n_expected, samples)
    rows = []
    for s in samples:
        mean = means[s.input_id]
        rows.append(
            Row(
                input_id=s.input_id,
                regime=s.regime,
                label=s.label,
                t_index=s.t_index,
                p=None if mean is None else calibrator.predict(mean),
            )
        )
    return rows


async def write_decisions(
    conn: sqlite3.Connection,
    writer: SqliteStorageWriter,
    fit: ArmFit,
    rows: list[Row],
    margin: float,
) -> None:
    """Persist the headline operating point into `decisions` and `was_used`.

    Valid replicas of an invalid sample get `was_used = 0` (spec §8). Other
    coverage targets live only in derived reports.
    """
    probs = load_probabilities(conn, fit.experiment_id)
    latency = completion_latency(load_calls(conn, fit.experiment_id))
    for row in rows:
        await writer.mark_used(
            fit.experiment_id,
            row.input_id,
            list(probs.get(row.input_id, {})),
            row.p is not None,
        )
        if row.p is None:
            continue
        decision = decide(row.p, margin)
        await writer.record_decision(
            experiment_id=fit.experiment_id,
            input_id=row.input_id,
            aggregate_score=row.p,
            final_confidence=abs(row.p - 0.5) + 0.5,
            final_decision=decision,
            is_correct=None if decision == "SKIP" else int(decision == row.label),
            total_latency=latency.get(row.input_id),
            early_stopped=0,
        )
```

```python
# src/metrics/report.py
"""Arm summaries and the A-vs-C comparison (spec §6.6, §7)."""

from __future__ import annotations

import json
from typing import Any

from src.aggregation.core import margin_grid
from src.experiments.config import Exp1Config, Pricing
from src.experiments.pipeline import ArmFit
from src.metrics.bootstrap import paired_block_ci
from src.metrics.core import (
    Row,
    accuracy_at_coverage,
    acted_accuracy_coverage,
    brier,
    log_loss,
    percentile,
    reliability,
    risk_coverage,
)
from src.storage.reader import CallRow, completion_latency


def arm_cost(calls: list[CallRow], pricing: Pricing | None) -> dict[str, Any]:
    """Token totals and cost; cost is None (never estimated) without pricing."""
    tokens_in = tokens_out = missing = 0
    for call in calls:
        usage = call.token_usage
        if not usage or "input_tokens" not in usage:
            missing += 1
            continue
        tokens_in += usage["input_tokens"]
        tokens_out += usage.get("output_tokens", 0)
    cost = None
    if pricing is not None:
        cost = (
            tokens_in * pricing.input_per_mtok + tokens_out * pricing.output_per_mtok
        ) / 1_000_000
    return {
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "calls_without_usage": missing,
        "cost_usd": cost,
    }


def _acc_cov(rows: list[Row], margin: float) -> dict[str, Any]:
    r = acted_accuracy_coverage(rows, margin)
    return {
        "accuracy": r.accuracy,
        "coverage_valid": r.coverage_valid,
        "coverage_all": r.coverage_all,
        "n_acted": r.n_acted,
    }


def _arm_summary(
    rows: list[Row], fit: ArmFit, cfg: Exp1Config, calls: list[CallRow]
) -> dict[str, Any]:
    targets = {
        key: {
            "margin": c.margin,
            "reached_target": c.reached,
            **_acc_cov(rows, c.margin),
        }
        for key, c in fit.margins.items()
    }
    headline = fit.margins[cfg.target_key(cfg.headline_coverage)].margin
    latencies = list(completion_latency(calls).values())
    n_valid = sum(r.p is not None for r in rows)
    return {
        "n_rows": len(rows),
        "n_valid": n_valid,
        "invalid_rate": (len(rows) - n_valid) / len(rows) if rows else 0.0,
        "targets": targets,
        "brier": brier(rows),
        "log_loss": log_loss(rows, cfg.logloss_delta),
        "reliability": reliability(rows),
        "by_regime_headline": {
            regime: _acc_cov([r for r in rows if r.regime == regime], headline)
            for regime in sorted({r.regime for r in rows})
        },
        "latency_p50": percentile(latencies, 0.5) if latencies else None,
        "latency_p95": percentile(latencies, 0.95) if latencies else None,
        "cost": arm_cost(calls, cfg.pricing),
    }


def _common_summary(
    common_a: list[Row],
    common_c: list[Row],
    fit_a: ArmFit,
    fit_c: ArmFit,
    cfg: Exp1Config,
) -> dict[str, Any]:
    grid = margin_grid(cfg.margin_step)
    curve_a, curve_c = risk_coverage(common_a, grid), risk_coverage(common_c, grid)
    targets: dict[str, Any] = {}
    for target in cfg.coverage_targets:
        key = cfg.target_key(target)
        ma, mc = fit_a.margins[key].margin, fit_c.margins[key].margin

        def stat(idx: list[int], ma: float = ma, mc: float = mc) -> float | None:
            a = acted_accuracy_coverage([common_a[i] for i in idx], ma).accuracy
            c = acted_accuracy_coverage([common_c[i] for i in idx], mc).accuracy
            return None if a is None or c is None else c - a

        targets[key] = {
            "A": _acc_cov(common_a, ma),
            "C": _acc_cov(common_c, mc),
            "matched_accuracy_A": accuracy_at_coverage(curve_a, target),
            "matched_accuracy_C": accuracy_at_coverage(curve_c, target),
            "diff_ci": paired_block_ci(
                len(common_a),
                cfg.bootstrap_block_len,
                cfg.bootstrap_resamples,
                cfg.bootstrap_seed,
                stat,
            ),
        }
    return {"targets": targets}


def compare_arms(
    rows_a: list[Row],
    rows_c: list[Row],
    fit_a: ArmFit,
    fit_c: ArmFit,
    cfg: Exp1Config,
    *,
    calls_a: list[CallRow],
    calls_c: list[CallRow],
    references: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Headline comparison on the common valid set; per-arm results alongside."""
    by_a = {r.input_id: r for r in rows_a}
    by_c = {r.input_id: r for r in rows_c}
    common_ids = sorted(
        (
            i
            for i, r in by_a.items()
            if r.p is not None and i in by_c and by_c[i].p is not None
        ),
        key=lambda i: by_a[i].t_index,
    )
    report: dict[str, Any] = {
        "n_labelled": len(rows_a),
        "n_common_valid": len(common_ids),
        "arms": {
            "A": _arm_summary(rows_a, fit_a, cfg, calls_a),
            "C": _arm_summary(rows_c, fit_c, cfg, calls_c),
        },
        "common": _common_summary(
            [by_a[i] for i in common_ids],
            [by_c[i] for i in common_ids],
            fit_a,
            fit_c,
            cfg,
        ),
        "references": references or {},
        "warnings": [],
    }
    for name, summary in report["arms"].items():
        if summary["invalid_rate"] > cfg.invalid_warn_rate:
            report["warnings"].append(
                f"arm {name}: invalid rate {summary['invalid_rate']:.1%} exceeds "
                f"{cfg.invalid_warn_rate:.1%}"
            )
    return report


def render_markdown(report: dict[str, Any]) -> str:
    """Compact text report: warnings first, then the common-set table."""
    lines = ["# Experiment 1 report", ""]
    for warning in report["warnings"]:
        lines.append(f"> WARNING: {warning}")
    lines += [
        f"labelled: {report['n_labelled']}, common valid: {report['n_common_valid']}",
        "",
        "| target | A acc | A cov | C acc | C cov | C-A 95% CI |",
        "|---|---|---|---|---|---|",
    ]
    for key, row in report["common"]["targets"].items():
        a, c = row["A"], row["C"]
        lines.append(
            f"| {key} | {a['accuracy']} | {a['coverage_valid']} | "
            f"{c['accuracy']} | {c['coverage_valid']} | {row['diff_ci']} |"
        )
    lines += ["", "```json", json.dumps(report["references"], indent=2), "```"]
    return "\n".join(lines)
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_metrics -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
venv/bin/black src tests && venv/bin/ruff check src tests
git add src tests
git commit -m "feat: ブロックbootstrap・fit/scoreパイプライン・比較レポートを追加する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 11: End-to-end mock run and `report` command

**Files:**
- Modify: `src/experiments/cli.py` (add the `report` command)
- Test: `tests/test_experiments/test_end_to_end.py`

**Interfaces:**
- Consumes: everything above.
- Produces: a verified mock-API path for `run` → `fit_arm` → `score_rows` → `compare_arms`, and CLI `report --config ... --a-experiment ... --c-experiment ... --split test`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_experiments/test_end_to_end.py
"""Whole pipeline against a state-aware fake client (no real API)."""

import zlib

import pytest
import typesafe_sdk as ts

from src.data.synthetic import SyntheticConfig, SyntheticSource
from src.experiments.config import Exp1Config
from src.experiments.pipeline import fit_arm, score_rows, write_decisions
from src.experiments.runner import ArmSpec, run_arm
from src.judges.jev_executor import JevStageExecutor
from src.metrics.report import compare_arms, render_markdown
from src.storage import db
from src.storage.reader import load_calls
from src.storage.writer import SqliteStorageWriter


class StateAwareClient:
    """P(HIGH) follows a 5-bar momentum signal plus a per-replica jitter."""

    async def system_one(self, *, state, questions, **kwargs):
        bars = state["bars"]
        signal = 1.0 if bars[-1] > bars[-6] else 0.0
        return ts.SystemOneResponse(
            model="jev-test",
            usage=ts.Usage(input_tokens=10, output_tokens=2),
            answers={
                name: ts.NoulAnswer(
                    noul=0.3 + 0.4 * signal + (zlib.crc32(name.encode()) % 7) * 0.01
                )
                for name in questions
            },
        )


class DropFirstReplicaClient(StateAwareClient):
    """Drops replica 0 from every response, so no C sample reaches N answers."""

    async def system_one(self, *, state, questions, **kwargs):
        response = await super().system_one(state=state, questions=questions)
        response.answers.pop("hl_judge#0", None)
        return response


CFG = Exp1Config(
    data=SyntheticConfig(
        seed=7,
        split_sizes={"pilot": 5, "calib": 60, "thresh": 60, "test": 60, "test_shift": 5},
    ),
    bootstrap_resamples=30,
    bootstrap_block_len=3,
)


async def _run_all(conn, writer, client, specs, source):
    executor = JevStageExecutor(client, writer)
    for spec in specs:
        for split in ("calib", "thresh", "test"):
            await run_arm(spec, source.samples(split), executor, writer, conn)


async def test_pipeline_end_to_end(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    writer = SqliteStorageWriter(conn)
    source = SyntheticSource(CFG.data)
    spec_a = ArmSpec(study_id="e", arm="A", horizon=5)
    spec_c = ArmSpec(study_id="e", arm="C", topology="batched", n_replicas=5, horizon=5)
    await _run_all(conn, writer, StateAwareClient(), [spec_a, spec_c], source)

    calib, thresh, test = (source.samples(s) for s in ("calib", "thresh", "test"))
    fit_a = await fit_arm(conn, writer, spec_a.experiment_id, 1, calib, thresh, CFG)
    fit_c = await fit_arm(conn, writer, spec_c.experiment_id, 5, calib, thresh, CFG)

    with pytest.raises(ValueError):  # frozen settings are never overwritten
        await fit_arm(conn, writer, spec_a.experiment_id, 1, calib, thresh, CFG)

    rows_a, rows_c = score_rows(conn, fit_a, test), score_rows(conn, fit_c, test)
    headline = CFG.target_key(CFG.headline_coverage)
    await write_decisions(conn, writer, fit_c, rows_c, fit_c.margins[headline].margin)
    n_decisions = conn.execute(
        "SELECT COUNT(*) FROM decisions WHERE experiment_id = ?",
        (spec_c.experiment_id,),
    ).fetchone()[0]
    assert n_decisions == sum(r.p is not None for r in rows_c) == len(test)
    used = conn.execute(
        "SELECT COUNT(*) FROM judge_logs WHERE experiment_id = ? AND was_used = 1",
        (spec_c.experiment_id,),
    ).fetchone()[0]
    assert used == 5 * len(test)

    report = compare_arms(
        rows_a,
        rows_c,
        fit_a,
        fit_c,
        CFG,
        calls_a=load_calls(conn, spec_a.experiment_id),
        calls_c=load_calls(conn, spec_c.experiment_id),
    )
    assert report["n_common_valid"] == len(test)
    assert report["warnings"] == []
    assert report["common"]["targets"]["1.00"]["A"]["accuracy"] is not None
    assert "Experiment 1 report" in render_markdown(report)


async def test_dropped_replicas_make_every_c_sample_invalid(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    writer = SqliteStorageWriter(conn)
    source = SyntheticSource(CFG.data)
    spec_c = ArmSpec(study_id="e", arm="C", topology="batched", n_replicas=5, horizon=5)
    await _run_all(conn, writer, DropFirstReplicaClient(), [spec_c], source)

    calib, thresh = source.samples("calib"), source.samples("thresh")
    # Every sample has 4 < N answers, so nothing is valid: fitting has no data
    # and fails loudly instead of averaging the survivors.
    with pytest.raises(ValueError):
        await fit_arm(conn, writer, spec_c.experiment_id, 5, calib, thresh, CFG)
```

- [ ] **Step 2: Run to verify**

Run: `venv/bin/pytest tests/test_experiments/test_end_to_end.py -v`
Expected: PASS if Tasks 1-10 are correct (this test is the integration check; if it fails, fix the earlier task's code, not the test, unless the test itself is wrong).

- [ ] **Step 3: Add the `report` command**

In `src/experiments/cli.py`, add the imports `from src.data.baselines import accuracy, fit_momentum, fit_regime_aware, majority_label`, `from src.experiments.pipeline import ArmFit, score_rows`, `from src.metrics.report import compare_arms, render_markdown`, `from src.storage.reader import load_calls`, plus this function and its subparser:

```python
def _report(args: argparse.Namespace) -> None:
    cfg = _load(args.config)
    source = SyntheticSource(cfg.data)
    conn = db.connect(cfg.db_path)

    def frozen_fit(experiment_id: str) -> ArmFit:
        row = conn.execute(
            "SELECT config_json FROM experiments WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        return ArmFit.model_validate(json.loads(row[0])["frozen"]["fit"])

    samples = source.samples(args.split)
    fit_a, fit_c = frozen_fit(args.a_experiment), frozen_fit(args.c_experiment)
    calib = source.samples("calib")
    momentum, regime_aware = fit_momentum(calib), fit_regime_aware(calib)
    references = {
        "majority": accuracy([majority_label(calib)] * len(samples), samples),
        "momentum": accuracy([momentum.predict(s.state) for s in samples], samples),
        "regime_aware": accuracy([regime_aware.predict(s) for s in samples], samples),
    }
    report = compare_arms(
        score_rows(conn, fit_a, samples),
        score_rows(conn, fit_c, samples),
        fit_a,
        fit_c,
        cfg,
        calls_a=load_calls(conn, args.a_experiment),
        calls_c=load_calls(conn, args.c_experiment),
        references=references,
    )
    print(render_markdown(report))
```

```python
    rep = sub.add_parser("report", help="compare A and C on one evaluation split")
    rep.add_argument("--config", required=True)
    rep.add_argument("--a-experiment", required=True)
    rep.add_argument("--c-experiment", required=True)
    rep.add_argument("--split", choices=["test", "test_shift"], default="test")
```

and in `main` add `elif args.command == "report": _report(args)`.

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest -q && venv/bin/python -m src.experiments.cli report --help`
Expected: all tests PASS; help shows the `report` options.

- [ ] **Step 5: Commit**

```bash
venv/bin/black src tests && venv/bin/ruff check src tests
git add src tests
git commit -m "feat: reportコマンドとend-to-endの検証を追加する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Review, docs, and checkpoint

**Files:**
- Modify: `src/data/README.md`, `src/experiments/README.md`, `src/aggregation/README.md`, `src/metrics/README.md` (replace the stub line with a 3-5 line English description linking the spec), `.ai/memory/TASKS.md`, `.ai/memory/CURRENT_STATE.md`

- [ ] **Step 1: Full quality gate**

Run: `venv/bin/black --check src tests && venv/bin/ruff check src tests && venv/bin/pytest -q`
Expected: all clean/passing.

- [ ] **Step 2: Review the code** — invoke the `ai-code-review` skill on `git diff develop...HEAD -- src` against decomposition, abstraction, separation of concerns, idiom, and security threat classes; fix findings with tests.

- [ ] **Step 3: Update docs** — replace each stub README with a short description (what the package does, entry points, link to the spec).

- [ ] **Step 4: Update the checkpoint** — invoke the `context-checkpoint` skill; in `TASKS.md` move the Experiment 1 implementation to done and add the human steps of Task 13 under "Waiting (human / external)"; in `CURRENT_STATE.md` record that the Experiment 1 code is implemented and the pilot is pending (keep it within the file's 60-line limit).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs: Experiment 1実装後のREADMEとcheckpointを更新する" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Human-run pilot and full run (not automated)

These steps spend real API budget and use the real credential; a human runs them (project rules). Claude must not run them.

- [ ] **Step 1: Prepare** — copy `configs/exp1.example.json` to `configs/exp1.json`, set `pricing` (with its source) if known, and make sure the credential is available in the local environment file (do not print it).

- [ ] **Step 2: Pilot** (small budget; adjust `--max-units`):

```bash
venv/bin/python -m src.experiments.cli run --config configs/exp1.json --arm C --topology batched --split pilot --max-units 60
venv/bin/python -m src.experiments.cli run --config configs/exp1.json --arm C --topology separate --split pilot --max-units 150
venv/bin/python -m src.experiments.cli run --config configs/exp1.json --arm A --run 1 --split pilot
venv/bin/python -m src.experiments.cli run --config configs/exp1.json --arm A --run 2 --split pilot
venv/bin/python -m src.experiments.cli pilot-stats --config configs/exp1.json --experiments exp1-C-batched
venv/bin/python -m src.experiments.cli pilot-stats --config configs/exp1.json --experiments exp1-C-separate
venv/bin/python -m src.experiments.cli pilot-stats --config configs/exp1.json --experiments exp1-A-run1 exp1-A-run2
```

- [ ] **Step 3: Decide** — if `negligible` is false for the chosen topology, fix N and topology and set the real split sizes (from the observed cost and variance). If `negligible` is true everywhere, stop and decide with Claude between the spec §5.4 fallbacks (each is a separately approved ablation); record the decision as an addendum to the spec.

- [ ] **Step 4: Full run** — run arms A (run 1 and run 2) and C (chosen topology) over `calib`, `thresh`, `test`, `test_shift`; freeze each arm once with `fit` (it also writes the headline decisions; the `report` command reads the frozen fit), e.g. `venv/bin/python -m src.experiments.cli fit --config configs/exp1.json --arm C --experiment exp1-C-batched`; use `--study-id` on `run` to keep pilot variants in their own study; then:

```bash
venv/bin/python -m src.experiments.cli report --config configs/exp1.json --a-experiment exp1-A-run1 --c-experiment exp1-C-batched --split test
venv/bin/python -m src.experiments.cli report --config configs/exp1.json --a-experiment exp1-A-run1 --c-experiment exp1-C-batched --split test_shift
```

- [ ] **Step 5: Record** the outcome in `.ai/memory/CURRENT_STATE.md` and `TASKS.md`.
