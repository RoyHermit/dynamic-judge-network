# Experiment 2: Role-Decomposed Fixed Judges (D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the indicator features, role/all-indicator Judges, Platt-calibrated arm pipeline, deterministic competitors, paired comparison, preregistered verdict and CLI needed to run baseline D against A' (and A, C, A'x5, L, M, Majority, Const) on ECB and a fresh-seed synthetic dataset.

**Architecture:** Reuse the Experiment 1 pipeline: the resumable runner writes every raw answer to sqlite, and everything else (calibration, margins, comparison, verdict) is recomputed offline from storage. The runner is generalised so an arm can supply a per-unit state (one state per request, so a role Judge never sees another role's data). Indicators, Platt scaling and logistic regression are pure Python with no new dependency.

**Tech Stack:** Python 3.11+ (venv), pydantic 2, `typesafe-sdk` 0.7.2 (`JevStageExecutor`), sqlite3, pytest + pytest-asyncio, black, ruff.

**Spec:** `docs/superpowers/specs/2026-10-19-experiment-2-role-decomposition-design.md` (section numbers below refer to it). It builds on `docs/superpowers/specs/2026-10-15-experiment-1-fixed-judges-average-design.md`.

## Global Constraints

- Python 3.11+ with `pip` + `venv`; run tools as `venv/bin/python -m ...` / `venv/bin/pytest`.
- `typesafe-sdk` 0.7.2 via `JevStageExecutor`; no LiteLLM; `retry_count` stays `None`.
- **No new dependencies**; do not modify `requirements.txt` (§9).
- Repo artifacts (code, comments, docstrings, docs) are English; chat is Japanese.
- Type hints on every function signature; docstrings on public functions; comments for non-obvious logic.
- Tests never call the real Jev API and never use real data; all data (including CSV fixtures) is generated from schemas (`mock-test-data` skill).
- Run `venv/bin/black src tests` and `venv/bin/ruff check src tests` before every commit.
- Work only on branch `feat/experiment-2-role-decomposition` (never `main`); never `git push`.
- Commit messages: `<type>: <summary>` (Japanese is fine, as in the existing log), ending with the trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Never read or print the local environment file or any credential. **Real API runs are human-only**, one separately authorised stage at a time (§9); no task in this plan calls the real API.
- Splits (§7): `pilot 30, calib 150, thresh 150, test 600, test_shift 300`, window 60, horizon 5, stride 5. Synthetic uses a new seed (not 0); study ids `exp2` (synthetic) and `exp2-ecb`.
- Indicators: closes only, past bars only, 60 closes / 59 one-bar log returns, values rounded to 4 decimals (§4). Population standard deviation everywhere (plan decision, fixed here so tests are exact).
- Roles are exactly Trend, Momentum, Mean-reversion, Volatility, Breakout (§4). D = five **separate** requests, never batched; A'x5 = five separate requests (§4).
- Primary metric: accuracy at full coverage, HIGH iff calibrated `p >= 0.5` (§5). Success: D-A' CI lower bound > 0 **and** point estimate >= +0.03; D-Majority, D-L, D-M CI lower bound > 0 (§5). Verdict table §11. These constants are frozen; never tuned.
- Platt: clip mean probability to [1e-4, 1-1e-4] before the logit, small L2 on the slope, slope >= 0, fallback to the `calib` base rate when inputs are constant / the fit fails / the data are perfectly separated, with the fallback recorded (§8). Never refit on `test`.
- Pilot stop rules (§9): any arm invalid rate > 5%; any NaN/inf indicator; a Judge whose probability std across pilot inputs < 0.01.
- `test_shift` is never part of the success rule and never used to choose anything (§9).

## Review Focus

Failure modes the spec implies but a happy-path test would miss (each has a test in the named task):

1. A flat window (all 60 closes equal) or a flat 20-bar range must give the defined degenerate indicator values, never NaN/inf or a crash (Task 1).
2. Single-class `calib`, constant mean probabilities, or perfectly separated `calib` must fall back to the base rate, record the fallback, and never raise (Tasks 3, 7).
3. A role's request must contain only that role's indicator keys, and a D sample with fewer than five valid answers is invalid, not averaged (Tasks 5, 7).
4. An eligibility set smaller than two bootstrap blocks (or empty) gives `ci = None`, which counts as "criterion not met" rather than raising (Tasks 8, 10).
5. Constant error vectors (e.g. a Judge that is always right/wrong after calibration) report correlation as `None` (undefined), never 0 (Task 9).

## File Structure

New:
- `src/features/__init__.py`, `src/features/indicators.py`: deterministic indicators, role definitions, state builders.
- `src/judges/definitions/indicator_judge.py`: `RoleJudge`, `AllIndicatorsJudge` (prompts, ids, `interpret`).
- `src/aggregation/platt.py`: `PlattCalibrator` with recorded fallback.
- `src/aggregation/logistic.py`: pure-Python L2 logistic regression `LogisticModel`.
- `src/data/competitors.py`: L, M, Majority, Const as `Row` producers.
- `src/experiments/exp2_config.py`: `Exp2Config`.
- `src/experiments/exp2_arms.py`: `Exp2ArmSpec` (arms `Ap`, `Ap5`, `D`) and spec lookup for A/C.
- `src/experiments/exp2_pipeline.py`: judge-subset means, Platt+isotonic fit, scoring.
- `src/metrics/paired.py`: full-coverage correctness, eligibility set, paired difference CI.
- `src/metrics/diagnostics.py`: per-Judge calibration, error correlation, leave-one-out.
- `src/experiments/verdict.py`: §5 success rule, §11 cross-dataset table.
- `src/experiments/exp2_pilot.py`: pilot stop-rule checks.
- `src/experiments/exp2_cli.py`: `run`, `pilot-check`, `fit`, `report`.
- `configs/exp2.example.json`, `configs/exp2-ecb.example.json`.
- Tests mirror each module under `tests/`.

Modified:
- `src/judges/definitions/high_low.py`: extract `parse_probability(answer)` (shared by all Judges).
- `src/experiments/runner.py`: arm-spec protocol with `state_for` and `judge_for`.
- `src/experiments/pipeline.py`: `write_decisions` accepts any fit exposing `experiment_id`.
- READMEs, `.ai/memory/TASKS.md`, `.ai/memory/CURRENT_STATE.md` (Task 12).

---

### Task 1: Indicators and role states

**Files:**
- Create: `src/features/__init__.py`, `src/features/indicators.py`
- Test: `tests/test_features/test_indicators.py`

**Interfaces:**
- Produces:
  - `ROLES: tuple[str, ...] = ("trend", "momentum", "mean_reversion", "volatility", "breakout")`
  - `ROLE_INDICATORS: dict[str, tuple[str, ...]]` (key names below)
  - `compute_indicators(closes: list[float]) -> dict[str, float]` (all 11 indicators, rounded to 4 dp; requires exactly 60 closes, else `ValueError`)
  - `role_state(closes: list[float], role: str) -> dict[str, float]` (only that role's keys)
  - `all_state(closes: list[float]) -> dict[str, float]` (union, same keys/precision)
  - `feature_vector(closes: list[float]) -> list[float]` (union in fixed key order, for L)

Indicator keys per role (§4): trend: `trend_slope_bp`, `close_vs_sma20_pct`, `close_vs_sma60_pct`; momentum: `ret5_pct`, `ret10_pct`, `ret20_pct`; mean_reversion: `zscore20`; volatility: `vol10_pct`, `vol59_pct`, `vol_ratio`; breakout: `range_pos20`.
Definitions: slope = OLS of `ln(close)` on index 0..59, times 1e4; SMA deviation = `(last / mean(last n) - 1) * 100`; `retK_pct = ln(c[-1]/c[-1-K]) * 100`; `zscore20 = (last - mean20) / pstdev20` over the last 20 closes; `volN_pct = pstdev(last N one-bar log returns) * 100` (N=10 and 59); `vol_ratio = vol10/vol59`; `range_pos20 = (last - low20) / (high20 - low20)`.
Degenerate (§4): zero variance gives slope 0, z-score 0, volatility 0, ratio 1; flat 20-bar range gives 0.5. A zero `vol59` gives ratio 1 even if `vol10` is also 0 (never divide by zero).

- [ ] **Step 1: Write the failing tests** in `tests/test_features/test_indicators.py`:
  - `test_flat_window_is_degenerate_not_nan`: closes `[1.1] * 60` gives `slope == 0`, `zscore20 == 0`, `vol10_pct == vol59_pct == 0`, `vol_ratio == 1`, `range_pos20 == 0.5`, every value finite (Review Focus 1).
  - `test_linear_log_growth_slope`: `closes[i] = 100 * exp(0.001 * i)` gives `trend_slope_bp == pytest.approx(10.0, abs=1e-3)` and `ret5_pct == pytest.approx(0.5, abs=1e-3)`.
  - `test_range_position_bounds`: strictly rising closes give `range_pos20 == 1.0`; strictly falling give `0.0`.
  - `test_no_lookahead`: changing a value outside the window is impossible by signature; instead assert `compute_indicators(closes)` is unchanged when called on `closes[:]` of a longer series' last 60 (a pure function of the 60 given closes) and that a wrong length raises `ValueError`.
  - `test_role_state_has_only_role_keys`: for every role, `set(role_state(c, role)) == set(ROLE_INDICATORS[role])`; `all_state` keys equal the union; the roles' key sets are pairwise disjoint.
  - `test_values_rounded_to_four_decimals`: `round(v, 4) == v` for all values of a random-walk fixture generated with `random.Random(1)`.
  - `test_feature_vector_order_matches_keys`: `feature_vector(c) == [all_state(c)[k] for k in ALL_KEYS]` with `ALL_KEYS` the module's fixed ordered tuple (export it).
- [ ] **Step 2: Run** `venv/bin/pytest tests/test_features/test_indicators.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `src/features/indicators.py` with the signatures above and export `ALL_KEYS: tuple[str, ...]`. Use `statistics.pstdev`/`math` only.
- [ ] **Step 4: Run** the same command. Expected: all PASS.
- [ ] **Step 5: Commit** `feat: Experiment 2の決定論的インジケーターと役割別stateを追加する`.

---

### Task 2: Indicator Judges

**Files:**
- Create: `src/judges/definitions/indicator_judge.py`
- Modify: `src/judges/definitions/high_low.py` (extract `parse_probability(answer: Answer) -> float` from `HighLowJudge.interpret`, raising `ValueError` exactly as today; `interpret` returns `Decision(value=parse_probability(answer))`)
- Test: `tests/test_judges/test_indicator_judge.py`

**Interfaces:**
- Consumes: `ROLES`, `ROLE_INDICATORS` (Task 1); `Question`, `Answer`, `Decision`, `State` from `src/judges/interface.py`.
- Produces:
  - `class RoleJudge(role: str, horizon: int)`: `judge_id == f"role_{role}"`, `judge_version == "role-1.0"`, `to_question(state) -> Question(kind="noul", ...)`, `interpret(answer) -> Decision`.
  - `class AllIndicatorsJudge(horizon: int, replica: int | None = None)`: `judge_id == "ap_judge"` or `f"ap_judge#{k}"`, `judge_version == "allind-1.0"`.
  - `def judge_from_id(judge_id: str, horizon: int) -> Judge` (for re-interpretation: `role_*`, `ap_judge[#k]`, `hl_judge[#k]`).

Prompt rule (§4): the question sentence is the Experiment 1 sentence with "the price bars in the state" replaced by "the indicators in the state"; each Judge prepends one short neutral description, "You are given <role name> indicators for a price series (...)." for `RoleJudge`, "You are given trend, momentum, mean-reversion, volatility and breakout indicators for a price series (...)." for `AllIndicatorsJudge`. The parenthesised list names the indicator keys. The two classes build the text from one shared helper, so they differ only in the role name and the key list. Fix the wording in this task; it is never changed after the pilot.

- [ ] **Step 1: Write failing tests**:
  - `test_prompts_identical_except_role_and_keys`: after substituting the role name and key list of a `RoleJudge("trend", 5)` prompt with those of `AllIndicatorsJudge(5)`, the two strings are equal.
  - `test_judge_ids_and_replicas`: ids `role_trend`, `ap_judge`, `ap_judge#3`; `judge_from_id` round-trips all three families and raises `ValueError` for an unknown id.
  - `test_interpret_rejects_invalid`: answers with `None`, NaN, `1.5`, `True`, or non-noul kind raise `ValueError`; `0.0` and `1.0` are accepted.
  - `test_highlow_still_interprets`: existing `tests/test_judges/test_high_low_judge.py` passes unchanged.
- [ ] **Step 2: Run** `venv/bin/pytest tests/test_judges -v`. Expected: new tests FAIL.
- [ ] **Step 3: Implement** the module and the `parse_probability` extraction.
- [ ] **Step 4: Run** `venv/bin/pytest tests/test_judges -v`. Expected: all PASS.
- [ ] **Step 5: Commit** `feat: 役割別JudgeとA'用の全インジケーターJudgeを追加する`.

---

### Task 3: Platt calibrator

**Files:**
- Create: `src/aggregation/platt.py`
- Test: `tests/test_aggregation/test_platt.py`

**Interfaces:**
- Produces:
  - `class PlattCalibrator(BaseModel)` with fields `intercept: float`, `slope: float`, `fallback: str | None` (None when fitted; else `"constant_input" | "single_class" | "separated" | "fit_failed"`), `base_rate: float`.
  - `PlattCalibrator.fit(ps: list[float], ys: list[float], l2: float = 0.01) -> PlattCalibrator` (never raises on degenerate data; empty input gives `fallback="single_class"`, `base_rate=0.5`)
  - `PlattCalibrator.predict(p: float) -> float` (fallback: returns `base_rate`)
  - `logit_clip(p: float) -> float` (clip to [1e-4, 1-1e-4] then logit)

Approach: minimise NLL + `l2 * slope**2` over (intercept, slope) with Newton steps on the two parameters (2x2 solve in pure Python); project the slope to >= 0 (if the unconstrained optimum has negative slope, refit with slope fixed at 0, i.e. intercept-only, and report that as an ordinary fit, not a fallback). Detect constant inputs (all logits equal), single-class labels and perfect separation (all class-0 logits below all class-1 logits, or the reverse) **before** fitting. Non-convergence in 50 iterations or a non-finite parameter gives `fit_failed`. `base_rate` is the `calib` HIGH share, clipped to [1e-4, 1-1e-4] for `predict` only.

- [ ] **Step 1: Write failing tests**:
  - `test_recovers_known_curve`: with `random.Random(0)` generate 2000 `(p, y)` where `P(y=1) = sigmoid(0.5 + 1.5 * logit(p))`; fitted slope within 0.2 of 1.5 (small L2 shrinks slightly) and intercept within 0.2 of 0.5; `fallback is None`.
  - `test_slope_never_negative`: labels anti-correlated with `p` give `slope == 0`, `fallback is None`, `predict` constant at the base rate.
  - `test_fallbacks_recorded` (Review Focus 2): constant `ps`, single-class `ys`, perfectly separated data, and empty input each give the named `fallback` and `predict(x) == base_rate` for any `x`, with no exception.
  - `test_extreme_probabilities_clipped`: `fit` and `predict` accept `0.0` and `1.0` without error and return values in (0, 1).
  - `test_round_trip_dict`: `PlattCalibrator.model_validate(c.model_dump()) == c`.
- [ ] **Step 2: Run** `venv/bin/pytest tests/test_aggregation/test_platt.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** as described.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Platt校正とフォールバック記録を追加する`.

---

### Task 4: Logistic regression L and deterministic competitors

**Files:**
- Create: `src/aggregation/logistic.py`, `src/data/competitors.py`
- Test: `tests/test_aggregation/test_logistic.py`, `tests/test_data/test_competitors.py`

**Interfaces:**
- Consumes: `feature_vector` (Task 1), `Sample`, `fit_momentum`, `majority_label` (`src/data/baselines.py`), `Row` (`src/metrics/core.py`).
- Produces:
  - `class LogisticModel(BaseModel)`: `means: list[float]`, `scales: list[float]`, `weights: list[float]`, `bias: float`, `l2: float`; `predict(x: list[float]) -> float`.
  - `fit_logistic(xs: list[list[float]], ys: list[float], l2: float) -> LogisticModel` (standardise on the given rows; a zero-scale column uses scale 1; full-batch Newton/IRLS, <= 100 iterations; `l2` on weights, not on the bias).
  - `fit_competitors(calib: list[Sample], thresh: list[Sample], l2_grid: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0, 100.0)) -> Competitors`, where `Competitors` is a model with `logistic: LogisticModel`, `chosen_l2: float`, `momentum: MomentumRule`, `majority: Label`, `const_p: float`.
  - `competitor_rows(c: Competitors, samples: list[Sample]) -> dict[str, list[Row]]` with keys `"L"`, `"M"`, `"Majority"`, `"Const"`; `p` for L is the model probability; for M and Majority `p` is `1.0`/`0.0` (hard prediction); for Const it is `const_p`. Deterministic arms are always valid (`p` never `None`).

`l2` is selected on `thresh` by lowest log loss (ties: larger `l2`); the model is fitted on `calib` only (chronological, §3). `const_p` is the `calib` HIGH share; Majority is `majority_label(calib)` (frozen development direction).

- [ ] **Step 1: Write failing tests**:
  - `test_logistic_learns_separable_signal`: 400 rows, `x = [z, noise]` from `random.Random(3)`, `y = z > 0`; accuracy >= 0.95 on a fresh 400-row draw.
  - `test_logistic_zero_variance_column_is_safe`: a constant column yields finite weights.
  - `test_stronger_l2_shrinks_weights`: `l2=100` gives a smaller weight norm than `l2=0.01` on the same data.
  - `test_competitors_use_calib_only`: `fit_competitors` called with `thresh` labels flipped changes only `chosen_l2`, not `majority`, `const_p` or `momentum`.
  - `test_competitor_rows_valid_and_aligned`: four keys, each list has `len(samples)` rows in order, no `p is None`.
  - Use synthetic samples from `SyntheticSource(SyntheticConfig(seed=7, split_sizes=...))`; no real data.
- [ ] **Step 2: Run** `venv/bin/pytest tests/test_aggregation/test_logistic.py tests/test_data/test_competitors.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** both modules.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat: ロジスティック回帰Lと決定論的競合(M, Majority, Const)を追加する`.

---

### Task 5: Generalised runner and Exp2 arm specs

**Files:**
- Create: `src/experiments/exp2_arms.py`
- Modify: `src/experiments/runner.py`, `src/experiments/pipeline.py` (type of `write_decisions`'s `fit` parameter only: a `Protocol` with `experiment_id: str`)
- Test: `tests/test_experiments/test_exp2_arms.py`; existing `tests/test_experiments/test_runner.py` must still pass unchanged.

**Interfaces:**
- Consumes: judges (Task 2), `compute`-level state builders (Task 1), `Sample`, `JudgeExecutor`.
- Produces in `runner.py`: `class ArmLike(Protocol)` with `experiment_id: str`, `units() -> list[tuple[int, list[Judge]]]`, `state_for(sample: Sample, stage_index: int) -> State`, `judge_for(judge_id: str) -> Judge`, `model_dump() -> dict`. `ArmSpec` gains `state_for` (returns `sample.state`) and `judge_for` (`HighLowJudge(self.horizon, replica_index(judge_id))`). `run_arm` and `finish_pending_interpretations` accept `ArmLike`, call `state_for` for every unit and use `judge_for` for re-interpretation. Behaviour for A and C is unchanged.
- Produces in `exp2_arms.py`:
  - `class Exp2ArmSpec(BaseModel)`: `study_id: str`, `arm: Literal["Ap", "Ap5", "D"]`, `n_replicas: int = 5`, `horizon: int = 5`; `experiment_id` is `f"{study_id}-Ap"`, `f"{study_id}-Ap5"`, `f"{study_id}-D"`.
  - `Ap`: one unit, stage 0, `[AllIndicatorsJudge(h)]`, state `all_state`. `Ap5`: `n_replicas` units, stage k, `[AllIndicatorsJudge(h, k)]`, state `all_state` (separate requests). `D`: five units, stage `ROLES.index(role)`, `[RoleJudge(role, h)]`, state `role_state(closes, role)`.
  - `n_expected(arm: str, n_replicas: int) -> int`: A 1, Ap 1, C/Ap5 `n_replicas`, D 5.
  - `arm_spec(study_id: str, arm: str, cfg: Exp2Config) -> ArmLike`: `"A"`->`ArmSpec(arm="A")`, `"C"`->`ArmSpec(arm="C", topology="batched")`, others `Exp2ArmSpec`.

`closes` is `sample.state["bars"]`. Provenance note: the exact state sent is a pure function of the stored bars (tested), so storage is unchanged.

- [ ] **Step 1: Write failing tests** with a recording fake client (copy the `FakeJevClient` pattern of `test_runner.py`, additionally recording `state` per request):
  - `test_d_sends_five_separate_requests_with_only_role_keys` (Review Focus 3): each request has exactly one question id `role_<r>`, and `set(state) == set(ROLE_INDICATORS[r])`; the union over the five requests covers all indicators; no request contains `bars`.
  - `test_ap_state_is_union_and_ap5_is_five_requests`: `Ap` sends one request with all 11 keys; `Ap5` sends five requests with ids `ap_judge#0..4`.
  - `test_states_are_pure_function_of_stored_bars`: running the same sample twice produces identical states.
  - `test_resume_skips_completed_stage`: after a run with `max_units=2` on `D`, a second run executes only the remaining `3 * n_samples` units and creates no duplicate calls.
  - `test_pending_interpretation_uses_judge_for`: delete an interpretation for a `role_trend` row, call `finish_pending_interpretations`, the value is restored without a client call.
  - `test_identity_mismatch_refuses_resume`: reusing an experiment id with a different `requested_model` raises `ValueError` (existing `_check_identity` behaviour, now exercised for `D`).
  - `test_n_expected`: values per arm as above.
- [ ] **Step 2: Run** `venv/bin/pytest tests/test_experiments -v`. Expected: new tests FAIL, old ones PASS.
- [ ] **Step 3: Implement** the protocol change in `runner.py` (`_IDENTITY_KEYS` stays; add no new keys) and `exp2_arms.py`.
- [ ] **Step 4: Run** `venv/bin/pytest tests -q`. Expected: everything PASS (Experiment 1 behaviour unchanged).
- [ ] **Step 5: Commit** `feat: runnerをarm単位のstate生成に一般化しExperiment 2のarm定義を追加する`.

---

### Task 6: Exp2 configuration and configs

**Files:**
- Create: `src/experiments/exp2_config.py`, `configs/exp2.example.json`, `configs/exp2-ecb.example.json`
- Test: `tests/test_experiments/test_exp2_config.py`

**Interfaces:**
- Produces `class Exp2Config(Exp1Config)` with defaults overridden/added: `study_id="exp2"`, `db_path="workspace/exp2.db"`, `data.split_sizes == {"pilot": 30, "calib": 150, "thresh": 150, "test": 600, "test_shift": 300}` (set in the example configs; the class default for `data` stays synthetic with these sizes and `seed=11`), plus `platt_l2: float = 0.01`, `min_gain: float = 0.03`, `degenerate_std: float = 0.01`, `pilot_invalid_max: float = 0.05`. `headline_coverage` and `coverage_targets` keep the Exp1 values (`[1.0, 0.8, 0.6]`, `0.8`) so the coverage-matched reports work.
- `configs/exp2-ecb.example.json`: study `exp2-ecb`, db `workspace/exp2-ecb.db`, `ecb_csv` path `data/eurofxref-hist.csv` column `USD`, §7 split sizes. `configs/exp2.example.json`: study `exp2`, `source: synthetic`, `seed: 11`, §7 split sizes. Local non-example configs stay git-ignored/untracked.

- [ ] **Step 1: Write failing tests**:
  - `test_example_configs_parse_with_spec_sizes`: both JSON files load into `Exp2Config` and have the §7 sizes; synthetic `seed != 0`.
  - `test_ecb_needs_6710_bars`: `total_bars(cfg.data) == 6710` for the ECB example (§7).
  - `test_min_gain_is_frozen_value`: `Exp2Config().min_gain == 0.03` (guards accidental tuning).
  - `test_block_len_guard_inherited`: `bootstrap_block_len=1` raises `ValidationError`.
- [ ] **Step 2: Run** `venv/bin/pytest tests/test_experiments/test_exp2_config.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** config class and the two JSON files.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Experiment 2の設定とexample configを追加する`.

---

### Task 7: Fit and score pipeline (Platt, isotonic sensitivity)

**Files:**
- Create: `src/experiments/exp2_pipeline.py`
- Test: `tests/test_experiments/test_exp2_pipeline.py`

**Interfaces:**
- Consumes: `PlattCalibrator` (Task 3), `IsotonicCalibrator`, `choose_margin`, `margin_grid`, `mean_probability`, `load_probabilities`, `writer.freeze_config`, `Row`.
- Produces:
  - `class Exp2Fit(BaseModel)`: `experiment_id: str`, `n_expected: int`, `exclude_judges: list[str]`, `platt: PlattCalibrator`, `isotonic: dict[str, list[float]]`, `margins: dict[str, MarginChoice]` (margins chosen on `thresh` from Platt-calibrated `p`), `degenerate: bool`.
  - `subset_means(conn, experiment_id: str, n_expected: int, samples: list[Sample], exclude_judges: frozenset[str] = frozenset()) -> dict[str, float | None]` (mean over the valid answers of judges not excluded; `None` unless exactly `n_expected` remain).
  - `async fit_exp2_arm(conn, writer, experiment_id: str, n_expected: int, calib, thresh, cfg: Exp2Config, *, allow_degenerate: bool = False) -> Exp2Fit` (freezes under key `"fit"`, same refusal semantics as Experiment 1).
  - `fit_unfrozen(conn, experiment_id, n_expected, calib, thresh, cfg, exclude_judges) -> Exp2Fit` (no freeze; used for D-noVol and leave-one-out, which are derived analyses).
  - `score_exp2(conn, fit: Exp2Fit, samples: list[Sample], *, calibrator: Literal["platt", "isotonic"] = "platt") -> list[Row]` (invalid keeps `p=None`).

- [ ] **Step 1: Write failing tests** (helpers: insert `judge_logs` rows through `SqliteStorageWriter` as `tests/test_storage/helpers_exp1.py` does):
  - `test_partial_d_sample_is_invalid` (Review Focus 3): four valid role answers for one input give `p is None`, and it counts as invalid, not averaged.
  - `test_exclude_judge_recomputes_from_stored_answers`: with `exclude_judges={"role_volatility"}` and `n_expected=4` the mean equals the mean of the other four; no call is made.
  - `test_fit_records_platt_fallback`: constant D means on `calib` produce `fit.platt.fallback == "constant_input"` and the fit still freezes (Review Focus 2).
  - `test_degenerate_fit_refused_by_default`: no valid calib sample raises `ValueError` and nothing is frozen; `allow_degenerate=True` freezes a fit with `degenerate=True` and all rows invalid.
  - `test_freeze_cannot_be_overwritten`: second `fit_exp2_arm` raises `ValueError` (existing `freeze_config` rule).
  - `test_isotonic_is_sensitivity_only`: `score_exp2(..., calibrator="isotonic")` differs from Platt output but `fit.margins` come from Platt.
  - `test_margins_use_thresh_not_calib`: changing `thresh` labels does not change `fit.platt`; changing `calib` does.
- [ ] **Step 2: Run** `venv/bin/pytest tests/test_experiments/test_exp2_pipeline.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Reuse `choose_margin` unchanged; coverage targets come from `cfg.coverage_targets`.
- [ ] **Step 4: Run** the same command plus `venv/bin/pytest tests -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Platt校正を主とするExperiment 2のfit/scoreを追加する`.

---

### Task 8: Paired comparison and eligibility set

**Files:**
- Create: `src/metrics/paired.py`
- Test: `tests/test_metrics/test_paired.py`

**Interfaces:**
- Consumes: `Row`, `paired_block_ci`.
- Produces:
  - `full_coverage_correct(row: Row) -> int` (HIGH iff `p >= 0.5`; 1 if equals label; raises on `p is None`).
  - `eligible_ids(arms: dict[str, list[Row]], llm_arms: list[str]) -> list[str]` (ids valid in every arm named in `llm_arms`, ordered by `t_index`; deterministic arms are not in `llm_arms`).
  - `class PairedDiff(BaseModel)`: `n: int`, `acc_x: float | None`, `acc_y: float | None`, `diff: float | None`, `ci: tuple[float, float] | None`.
  - `paired_accuracy_diff(x: list[Row], y: list[Row], ids: list[str], cfg: Exp2Config) -> PairedDiff` (x minus y on `ids`; moving-block bootstrap with `cfg.bootstrap_block_len/resamples/seed`; `n == 0` gives all `None`).

- [ ] **Step 1: Write failing tests**:
  - `test_p_exactly_half_predicts_high`: `p=0.5`, label HIGH -> 1; label LOW -> 0 (primary metric ignores `SKIP`, §5).
  - `test_eligibility_is_intersection_over_llm_arms_only`: an invalid row in `Ap5` removes the id even if D and A' are valid; an always-valid `L` never shrinks the set.
  - `test_diff_ci_excludes_zero_for_clear_gain`: x correct on 80%, y on 60% of 400 time-ordered rows (fixed pattern) -> `ci[0] > 0` and `diff == pytest.approx(0.2)`.
  - `test_small_or_empty_set_gives_none_ci` (Review Focus 4): fewer than `2 * block_len` ids gives `ci is None` and `diff` still computed; empty set gives all `None`.
  - `test_pairing_uses_same_indices`: identical rows for x and y give `diff == 0` and a CI that contains 0.
- [ ] **Step 2: Run** `venv/bin/pytest tests/test_metrics/test_paired.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat: 完全カバレッジ精度のペア比較と適格集合を追加する`.

---

### Task 9: Diagnostics

**Files:**
- Create: `src/metrics/diagnostics.py`
- Test: `tests/test_metrics/test_diagnostics.py`

**Interfaces:**
- Consumes: `PlattCalibrator`, `Row`, `brier`.
- Produces:
  - `judge_rows(conn, experiment_id, samples, platt: PlattCalibrator, judge_id: str) -> list[Row]` (calibrated rows of one Judge; invalid -> `p=None`).
  - `error_vector(rows: list[Row]) -> list[int]` (1 if the calibrated prediction `p >= 0.5` is wrong).
  - `safe_correlation(a: list[float], b: list[float]) -> float | None` (Pearson; `None` if either series is constant or lengths < 2; never 0 for undefined).
  - `class JudgeDiagnostics(BaseModel)`: `accuracy`, `brier`, per judge.
  - `mean_pairwise_correlation(vectors: list[list[float]]) -> float | None` (mean of the defined pairwise correlations; `None` if none defined).
  - `pairwise_disagreement(rows_by_judge: dict[str, list[Row]]) -> dict[tuple[str, str], float]`.
  - `leave_one_out(...)`: for each role, `fit_unfrozen` (Task 7) with that role excluded and `score_exp2`, returning accuracy at full coverage on the supplied ids next to D's.

Each Judge's Platt calibrator is fitted on `calib` only, per Judge (§6). Residual correlation uses `p - label` of the calibrated probabilities.

- [ ] **Step 1: Write failing tests**:
  - `test_constant_error_vector_is_undefined` (Review Focus 5): two always-correct Judges give `safe_correlation == None` and `mean_pairwise_correlation == None`, not `0`.
  - `test_identical_errors_correlate_one`: replicas with the same errors give `1.0`; independent fixed patterns give a value within 0.1 of 0.
  - `test_per_judge_calibration_changes_error_definition`: a Judge whose raw `p` is always < 0.5 (Experiment 1 bias) but informative gets a non-constant calibrated error vector; the raw-0.5 version would be constant.
  - `test_leave_one_out_matches_manual_mean`: excluding one role equals the mean of the other four on a hand-built DB.
  - `test_disagreement_symmetric_and_in_unit_interval`.
- [ ] **Step 2: Run** `venv/bin/pytest tests/test_metrics/test_diagnostics.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Judge別校正・誤り相関・leave-one-out診断を追加する`.

---

### Task 10: Success rule and cross-dataset verdict

**Files:**
- Create: `src/experiments/verdict.py`
- Test: `tests/test_experiments/test_verdict.py`

**Interfaces:**
- Consumes: `PairedDiff` (Task 8), `Exp2Config`.
- Produces:
  - `class DatasetVerdict(BaseModel)`: `passed: bool`, `criteria: dict[str, bool]` keyed `"D>A' (+3pt)"`, `"D>Majority"`, `"D>L"`, `"D>M"`, `attributable: bool | None` (D>A'x5 CI above 0; `None` if A'x5 absent), `notes: list[str]`.
  - `evaluate_dataset(d_vs_ap: PairedDiff, d_vs_majority: PairedDiff, d_vs_l: PairedDiff, d_vs_m: PairedDiff, d_vs_ap5: PairedDiff | None, min_gain: float) -> DatasetVerdict`. Criterion 1: `ci is not None and ci[0] > 0 and diff >= min_gain`; criteria 2: `ci is not None and ci[0] > 0`. `ci is None` is "not met" with a note.
  - `combine(ecb: DatasetVerdict, synthetic: DatasetVerdict) -> tuple[str, str]` returning (verdict label, wording) per the §11 table: both pass `"Strong success"`; ECB only `"Exploratory success"`; synthetic only `"Mechanism works, no real-data evidence"`; neither `"Failure"`. The strong-success wording adds the decomposition-attribution sentence only if `ecb.attributable and synthetic.attributable`; otherwise it states the gain is not separable from replication/compute.

- [ ] **Step 1: Write failing tests**:
  - `test_gain_gate_applies_only_to_d_vs_ap`: D-A' CI above 0 with `diff=0.025` fails criterion 1; D-Majority with `diff=0.01` and CI above 0 passes criterion 2.
  - `test_all_four_must_hold`: each single failing criterion makes `passed False`.
  - `test_none_ci_is_not_met_not_error` (Review Focus 4).
  - `test_verdict_table`: four combinations map to the four labels.
  - `test_attribution_wording`: strong success without `attributable` says "not separable"; with it says the gain is due to role decomposition.
  - `test_missing_ap5_leaves_attribution_none`.
- [ ] **Step 2: Run** `venv/bin/pytest tests/test_experiments/test_verdict.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Constants come from arguments only (no module-level tuning knobs).
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat: 事前登録の成功判定とデータセット横断の判定表を追加する`.

---

### Task 11: Pilot stop-rule checks

**Files:**
- Create: `src/experiments/exp2_pilot.py`
- Test: `tests/test_experiments/test_exp2_pilot.py`

**Interfaces:**
- Consumes: `load_probabilities`, `compute_indicators`, `Sample`, `Exp2Config`.
- Produces:
  - `class PilotCheck(BaseModel)`: `stop: bool`, `reasons: list[str]`, `invalid_rate: dict[str, float]` (per arm experiment id), `judge_std: dict[str, float | None]`, `uninformative_roles: list[str]`.
  - `pilot_check(conn, experiments: dict[str, int], pilot: list[Sample], cfg: Exp2Config) -> PilotCheck` where `experiments` maps experiment id to `n_expected`. Rules (§9): `stop` if any arm's invalid rate > `cfg.pilot_invalid_max`; if any indicator on any pilot sample is non-finite; if any Judge's probability std across pilot inputs is < `cfg.degenerate_std` (that Judge id goes into `uninformative_roles` and the reason is written, never hidden).

- [ ] **Step 1: Write failing tests**:
  - `test_invalid_rate_above_five_percent_stops`: 2 of 30 invalid (6.7%) stops; 1 of 30 (3.3%) does not.
  - `test_constant_judge_probability_stops_and_names_role`: `role_trend` always `0.3` -> `stop`, `uninformative_roles == ["role_trend"]`, reason mentions the role.
  - `test_nonfinite_indicator_stops`: a pilot sample with `bars` containing a zero close yields a non-finite log return -> stop with a reason (use `compute_indicators` raising/propagating; the check must catch `ValueError`/non-finite and stop, not crash).
  - `test_healthy_pilot_does_not_stop`.
- [ ] **Step 2: Run** `venv/bin/pytest tests/test_experiments/test_exp2_pilot.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Thresholds only from `cfg`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat: pilotの停止規則チェックを追加する`.

---

### Task 12: CLI, report, end-to-end test and docs

**Files:**
- Create: `src/experiments/exp2_cli.py`, `src/experiments/exp2_report.py`
- Test: `tests/test_experiments/test_exp2_end_to_end.py`, `tests/test_experiments/test_exp2_report.py`
- Modify: `src/experiments/README.md`, `.ai/memory/TASKS.md`, `.ai/memory/CURRENT_STATE.md`
- Create: `docs/superpowers/plans/exp2-runbook.md` (staged human-run commands)

**Interfaces:**
- Consumes: everything above; `JevStageExecutor`, `Settings`, `load_source`, `dataset_identity`.
- Produces `exp2_cli.main(argv)` with subcommands:
  - `run --config C --arm {A,C,Ap,Ap5,D} --split S [--max-units N]` (spends API budget; human-only; mirrors Exp1 `_run`, uses `arm_spec`).
  - `pilot-check --config C` (offline; prints `PilotCheck` JSON; exit code 1 when `stop`).
  - `fit --config C --arm ARM [--decisions-split test|test_shift] [--allow-incomplete] [--allow-degenerate]` (checks dataset identity and completeness of calib/thresh units, freezes the Platt fit, writes decisions).
  - `report --config C --split test|test_shift [--arms ...]` (offline) printing the markdown from `exp2_report.render_markdown`.
- `exp2_report.build_report(...)` returns a dict with, per arm: invalid rate, coverage over all labelled candidates, accuracy at full coverage, matched accuracy at 0.8, Brier and log loss (raw and calibrated), reliability; plus paired comparisons D-A', D-Majority, D-L, D-M, D-A'x5, D-A, D-C, D-Const, D-noVol vs D; diagnostics (Task 9); isotonic sensitivity; cost/latency per arm (`arm_cost`); and the notes "ECB result is exploratory with respect to prior knowledge" and "bootstrap intervals condition on the frozen calibrator and margins". `test_shift` reports only D, A', L, M, Majority and is labelled secondary. `report` on `test` also prints the §5 `DatasetVerdict`; `combine` is exposed as `python -m src.experiments.exp2_cli verdict --ecb-config ... --synthetic-config ...`.
- The runbook lists the four human-authorised stages with exact commands and call counts from §9 (pilot 390, stage 2: 5,400, stage 3: 6,300, stage 4: 1,800 per dataset), the pilot-check gate before stage 2, `fit` before `report`, and states that no stage runs without separate human approval.

- [ ] **Step 1: Write failing tests**:
  - `test_end_to_end_synthetic_with_fake_client`: small splits (e.g. `pilot 3, calib 6, thresh 6, test 30, test_shift 6` with `bootstrap_block_len=1` is not allowed, so use `block_len=12` and `test` >= 24 for a CI), fake client returning role-dependent probabilities from a seeded `random.Random`; run all five LLM arms over all splits, `pilot-check`, `fit` each arm, `report` on `test`; assert the report has every comparison key, the verdict structure, and that A and C reuse the Experiment 1 specs (`exp2-A-run1`, `exp2-C-batched`). No network.
  - `test_cli_run_refuses_without_credentials_message`: `run` with the credential absent fails fast through `Settings.load()` (existing behaviour) without calling the client.
  - `test_report_marks_ecb_exploratory_and_ci_assumption`: markdown contains both notes.
  - `test_report_test_shift_has_only_secondary_arms`.
  - `test_fit_refuses_incomplete_run`: dropping one `thresh` call makes `fit` raise unless `--allow-incomplete`.
  - `test_total_calls_per_sample_is_13`: counting requests across arms A, C, Ap, Ap5, D for one sample gives 13 (§9).
- [ ] **Step 2: Run** `venv/bin/pytest tests/test_experiments -v`. Expected: new tests FAIL.
- [ ] **Step 3: Implement** CLI and report; keep each CLI function a thin wrapper over tested library calls. Write the runbook and update docs: tick/replace the Experiment 2 line in `TASKS.md`, update the "Next step" and branch status in `CURRENT_STATE.md` (keep it within 60 lines), add the new modules to `src/experiments/README.md`.
- [ ] **Step 4: Verify** `venv/bin/black src tests && venv/bin/ruff check src tests && venv/bin/pytest tests -q`. Expected: all clean/PASS (Experiment 1's 30 tests included). Then run the `ai-code-review` skill checklist on the diff before declaring done.
- [ ] **Step 5: Commit** `feat: Experiment 2のCLI・レポート・runbookを追加する`.

---

## Self-Review

- **Spec coverage:** §3 arms -> Tasks 4, 5; §4 indicators/roles/prompts/no-batching -> Tasks 1, 2, 5; §5 rule/eligibility/attribution -> Tasks 8, 10; §6 diagnostics -> Task 9; §7 data/sizes/seeds -> Task 6; §8 Platt/isotonic/margins/bootstrap note -> Tasks 3, 7, 12; §9 stop rules, staging, call counts, no new deps -> Tasks 11, 12 (runbook); §11 verdict -> Task 10. D-noVol and leave-one-out -> Tasks 7, 9.
- **Type consistency:** `Exp2Fit`, `Row`, `PairedDiff`, `ArmLike`, `n_expected(arm, n_replicas)` and judge ids (`role_*`, `ap_judge[#k]`, `hl_judge[#k]`) are named identically wherever they appear.
- **Not in the plan:** real API runs (human-only stages), merging branches into `develop`, and pinning the abstraction-input URLs; the untracked `configs/exp1-ecb.json` is left for the owner.
