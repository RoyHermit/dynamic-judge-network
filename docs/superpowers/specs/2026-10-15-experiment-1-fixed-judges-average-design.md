# Experiment 1: Fixed Judges + Average — Design

Date: 2026-10-15
Status: revised after Codex review (2026-10-15)
Builds on: `2026-09-27-project-foundation-design.md` (code-level truth for
`Judge`, `JevStageExecutor`, storage). Research context: baselines A–F in
`docs/context/djn-research-direction-update.md` §19–21.

## 1. Purpose and scope

Establish baselines **A** (single Judge) and **C** (one Judge definition
replicated N times, fixed average) on identical data, plus a measurement
foundation (accuracy, coverage, calibration, latency, cost) whose logs can
be reused unchanged when the dynamic DJN (E) is built.

- C is a **replication ensemble**: N evaluations of one logical Judge. It
  does not measure the benefit of role diversity (that is D).
- Hypothesis (deliberately weak): averaging N replicas improves
  accuracy-at-coverage and calibration over a single evaluation (A).
- Out of scope: B, D, dynamic activation, Activation Waves, Evidence State,
  graph, escalation, runtime, public-data loader (only the `DataSource`
  seam is defined), provider comparison, and the `Answer.probabilities`
  extension (deferred to the first experiment that uses Choice/Score
  questions; this experiment uses Noul only).
- Synthetic success only demonstrates **pipeline validity**, not a
  research result.

## 2. Principles

1. Separate paid execution from free analysis. Every raw Judge answer is
   stored; aggregation, calibration, thresholds, and metrics are recomputed
   offline from storage. Threshold sweeps cost no API calls.
2. No silent repair. Missing or invalid answers are counted, never
   averaged around or clipped.
3. Calibration and thresholds use validation splits only and are frozen
   before the test split is evaluated.
4. Add one mechanism at a time; this experiment adds none beyond
   replication.

## 3. Units

| Unit | Responsibility | Depends on |
|---|---|---|
| `src/data/` | `DataSource` protocol; seeded synthetic generator; labelling, splits, embargo | — |
| `src/judges/definitions/` | High/Low Judge (Noul) | `interface.py` |
| `src/experiments/` | Runner, replication topology, pilot, resumable execution | data, judges, storage |
| `src/aggregation/` | Mean of P(HIGH), calibration, margin → HIGH/LOW/SKIP | storage |
| `src/metrics/` | Metrics and reports | storage, aggregation |

Existing `JevStageExecutor` and the five storage tables are reused. No new
tables: experiment settings go to `experiments.config_json`, inputs and
ground truth to `inputs`, raw answers to `judge_logs.raw_answer_json`,
final decisions to `decisions`.

### 3.1 Result identity

`decisions` holds one row per `(experiment_id, input_id)`, so every
independently scored arm gets its **own `experiment_id`**:

- `exp1-A-run1`, `exp1-A-run2` (the two repeat runs of A);
- `exp1-C-batched`, `exp1-C-separate`.

Each `config_json` carries a shared `study_id`, its `arm`, `topology`, and
`run` fields. Coverage targets (§6.4) are not stored as separate
experiments: margins per target live in the arm's frozen `config_json`
and are applied at analysis time, producing derived result tables outside
`decisions` (reports are recomputed, never stored as decisions).

### 3.2 Writer and executor extensions required

The existing code does not yet support everything this spec promises. The
implementation plan must include:

- executor and runner forward `model` and `extra_body` and capture the
  response's returned model name (currently discarded);
- a writer method to update/freeze `experiments.config_json`;
- writer population of `was_used` and the usage fields defined in §8;
- a replica mapping so the runner can identify which logical replica a
  `judge_logs` row belongs to (encoded in `judge_id` `hl_judge#k`).

## 4. Data

### 4.1 Sample

`Sample(input_id, state, label, split, regime)`.

- `state`: the last W bars up to time t only (e.g. `{"bars": [...]}`).
  Never contains future bars.
- `label`: sign of the return from t to t+H (`HIGH` or `LOW`).
- `regime`: analysis metadata only; never present in `state` or the Judge
  prompt.

Initial parameters W=60, H=5 (configuration, not constants).

### 4.2 Synthetic generation (seeded)

| Regime | Process | Purpose |
|---|---|---|
| trend | constant drift + noise | signal |
| mean-reversion | Ornstein–Uhlenbeck | signal (reverse direction) |
| random walk | no drift | no signal; accuracy ≈ 50% is correct |
| high-noise | weak signal, large noise | cases where SKIP should pay off |

### 4.3 Labelling

Samples whose return is exactly 0 or has absolute value below ε are
**excluded** (no label). The excluded count is recorded in `config_json`.
ε is configuration.

### 4.4 Splits and leakage control

Contiguous chronological blocks: `pilot` (separate small series),
`calib`, `thresh`, `test`, and `test_shift`. There is no train split
(nothing is trained).

- `calib`: fits the probability calibrator.
- `thresh`: selects margins; separate from `calib` to limit overfitting.
- `test_shift`: regime parameters outside the range seen in `calib` and
  `thresh` (e.g. larger noise), to check calibration robustness.
- Embargo of at least W+H bars between consecutive splits so that no
  window or label crosses a split boundary.
- Sample stride within a split is at least H so labels do not overlap.
  Confidence intervals use block bootstrap.
- Split sizes are decided **after the pilot** (cost and variance).

### 4.5 Reference baselines

Majority class; a deterministic momentum rule (no LLM) whose parameters
are fitted on `calib` only; a regime-aware predictor that applies the
known per-regime optimal direction rule. The regime-aware predictor is a
reference point, not a guaranteed upper bound. Needed to interpret any
synthetic result.

### 4.7 Data contract

The generator is fully specified by a recorded configuration so a dataset
can be rebuilt from `config_json` alone:

- per-regime process parameters (drift, OU mean/rate, volatility), the
  regime schedule (contiguous segments, segment lengths) and the seed;
- return unit: log-return of close; price levels are derived from a
  fixed start value;
- ε and the tie rule (§4.3), W, H, stride, embargo length;
- the regime and split of every sample, persisted in
  `inputs.input_features_json` alongside `state`, with the label in
  `inputs.ground_truth`.

`test_shift` parameter ranges are declared explicitly (e.g. volatility
multiplier outside the `calib`/`thresh` range) and recorded.

### 4.6 Public data (later)

Same `Sample` schema, chronological date blocks, same embargo rule. A
human verifies data licensing before adoption.

## 5. Judge and execution

### 5.1 Judge definition

Noul question: "Is the close at bar t+H higher than at bar t?" `interpret`
returns `Decision.value = P(HIGH)` (the Noul probability). This avoids
averaging Choice `confidence`, which is the confidence of the *selected*
label and is not P(HIGH).

### 5.2 `Answer` extension (deferred)

Preserving the Choice probability vector (`Answer.probabilities`) was
agreed in principle but is **deferred** until an experiment uses Choice or
Score questions. Experiment 1 uses Noul only, where `raw_probability`
already is P(HIGH). The interface stays unchanged here.

### 5.3 Topologies

- **A**: one standalone question per request. Run twice per input as
  separate experiments (`run1`, `run2`, §3.1) to estimate repeat
  variability. The headline A result is `run1` (fixed in advance); `run2`
  is used only for the variability estimate. A is never ensembled and the
  better run is never selected. A uses its own calibrator and margins,
  fitted on `calib`/`thresh` from `run1`.
- **C**: N=5 replicas with IDs `hl_judge#0`…`#4` (the executor rejects
  duplicate IDs), same `judge_version`. Two execution topologies:
  - *batched*: N questions in one `run_stage` call;
  - *separate*: N independent requests (stage_index = replica index).

### 5.4 Pilot (gate before fixing N and topology)

The Jev SDK 0.7.2 exposes no temperature/seed control (only `model` and an
untyped `extra_body` whose server-side effect is unverified), and answers
are model-reported probabilities, so identical requests may return
near-identical values. On the `pilot` split measure, for batched, separate,
and optional `extra_body` variants: variance of P(HIGH) across replicas,
replica disagreement rate, and error correlation.

Decision rule: if replica variance is negligible, C as specified does not
test averaging. The fallbacks — (a) multiple models (`model` override;
couples with the provider axis), (b) equivalent input perturbations
(paraphrased prompt, rounded or reordered-equivalent state), or (c) drop
replication and reopen the B/D scope question — each introduce an extra
mechanism. They are **separately approved ablations with their own
hypotheses**, not part of this spec. The choice is made with the human
after the pilot and recorded in an addendum to this spec.

## 6. Aggregation and decisions

1. Mean of the N replica P(HIGH) values. If fewer than N valid answers,
   the sample is **invalid** for that arm (reported as failure rate,
   distinct from SKIP); survivors are not averaged.
2. Calibrator (initial choice: isotonic) fitted on `calib` only, **one per
   arm**. Inputs outside the fitted range are clamped to the nearest fitted
   value (no extrapolation).
3. Decision on calibrated p with margin m: `HIGH` if `p ≥ 0.5 + m`, `LOW`
   if `p ≤ 0.5 − m`, otherwise `SKIP`. Boundaries are inclusive on the
   HIGH/LOW side and defined in one place in code.
4. m is chosen on `thresh` as the smallest margin whose coverage is **at
   least** the target (e.g. 100%, 80%, 60%). Isotonic plateaus can make a
   target unattainable exactly; targets are therefore approximate. Plateau
   ties are broken deterministically by taking the first margin on a
   fixed ascending grid that meets the target.
5. Calibrators and margins are frozen and written to `config_json` before
   `test` and `test_shift` are scored.
6. Comparisons use the **achieved** coverage on the evaluated split (frozen
   margins give different coverages on `test`/`test_shift`), reported next
   to each result. Matched-coverage comparison interpolates each arm's
   risk–coverage curve at common coverage levels and states when an arm
   cannot reach a level.
7. Probabilities are clipped to `[δ, 1−δ]` (δ configurable, e.g. 1e-6) only
   for log-loss computation; the clipping is reported, and stored values
   are never modified.

### 6.1 Common-sample comparison

C needs all N answers, A needs one, so failures can be selective. The
headline A-vs-C comparison uses the **common valid set** (samples valid
for both arms). Arm-specific results over each arm's own valid set are
reported alongside, with each denominator stated. Invalid rates are
reported per arm; coverage is computed over valid samples and also over
all labelled samples (counting invalid as non-acted).

## 7. Metrics

- Accuracy among acted samples and coverage; risk–coverage curve;
  matched-coverage A vs C comparison.
- Brier score and log loss over all valid probabilities; reliability
  plots; per-class results.
- Paired A–C differences with block-bootstrap confidence intervals.
  Method: moving-block bootstrap over the time-ordered samples of a split
  (block length ≥ W/stride so overlapping input windows stay together; also
  never splitting a regime segment across blocks when avoidable), paired
  resampling (the same blocks for A and C), conditioning on the frozen
  calibrators and margins (intervals describe test-set sampling noise, not
  calibration uncertainty). Block length and number of resamples are
  recorded.
- Invalid-sample rate per arm; latency percentiles.
- Cost: measured token usage × pricing provenance from `config_json`, per
  input and per acted input, including failed calls that returned usage.
  If usage or pricing is unavailable the cost is reported as unavailable,
  never estimated silently. Ensemble completion time is defined per
  topology: *batched* = the single call's latency; *separate* = the sum of
  call latencies when run sequentially, or the maximum when run
  concurrently (the runner records which). A's repeat run is counted as a
  separate arm, not added to A's cost.
- Breakdowns by regime and by `test_shift`.
- Reference baselines from §4.5.
- Latency uses `calls.latency`. `judge_logs.judge_latency` repeats the
  request latency per Judge and must never be summed.

## 8. Logging

Reuses existing tables. `config_json` additionally records: dataset and
split versions, seeds, excluded-sample counts, calibrator parameters,
margins, requested and returned model, pricing provenance, topology,
replica mapping.

Usage semantics follow direction-update §11 and are **per replica row**,
not assumed equal:

- *requested*: a replica was included in a request (every replica of a
  valid run);
- *fetched*: a valid answer came back (absent when the call failed or the
  SDK dropped the answer);
- *activated*: always true in A/C (fixed execution, no gating);
- *used*: the replica's value entered the aggregate (`judge_logs.was_used`
  = 1); an otherwise valid replica of an invalid sample has
  `was_used = 0`.

Only `was_used` exists as a column today; the other three are derived from
`calls.status`, presence of a `judge_logs` row, and `interpret_error`
rather than new columns. The writer populates `was_used` after
aggregation, as part of the extensions in §3.2.

## 9. Error handling

| Event | Handling |
|---|---|
| `TypeSafeError` on a call | Keep existing behavior: `calls.status="error"`, sample invalid; no extra retry (`retry_count` stays `None`) |
| Answer dropped by SDK | Replica recorded as missing; C sample invalid |
| `interpret` raises | Existing: `interpret_error` recorded; replica invalid |
| Probability outside [0, 1] or NaN | Replica invalid; value is not clipped |
| Unlabelled sample (tie / below ε) | Excluded at generation; count recorded |
| Interrupted run | See §9.1 |
| Invalid rate above 5% (configurable) | Warning at the top of the report; never silently dropped from metrics |

### 9.1 Resumability

`call_id` is a fresh UUID, so resumption keys on the logical unit
`(experiment_id, input_id)` for batched C, A runs, and on
`(experiment_id, input_id, replica)` for separate C. A unit is **complete**
when its call is recorded and either all expected `judge_logs` rows exist
or the call is recorded as `status="error"` (a terminal failure; failed
calls are not retried automatically, so a re-run does not pay again).

- Stored `judge_logs` rows whose interpretation is missing are
  re-interpreted from the stored raw answer, with no new API call.
- A batched call that returned only some answers is complete (the missing
  replicas are terminal drops, §9 table).
- Unavoidable window: a crash between the provider response and the
  `record_call` write loses that paid call; on resume the unit is re-run.
  This is accepted; such calls are not detectable, so the cost report
  notes that it may under-count by the number of crashes.

## 10. Testing

No real API calls; all data is generated from schemas (`mock-test-data`).

- Data: same seed → same series; `state` excludes future bars; embargo
  holds; ties/ε exclusion recorded; momentum rule ≈ 50% on random walk
  (leak/bug detector).
- Judge: `to_question` builds a Noul question; `interpret` returns P(HIGH)
  from `raw_probability`; out-of-range or NaN values are rejected.
- Execution (mock Jev client): replica IDs, both topologies, missing and
  error handling, resume skips complete units and re-interprets stored
  raw answers without a new call, per-arm `experiment_id`s do not collide
  in `decisions`, `model`/`extra_body` forwarded and returned model
  captured.
- Aggregation: no averaging of survivors; boundary inequalities at
  `p = 0.5 ± m`; margins derived from coverage targets without touching
  test data.
- Metrics: hand-computable tables for accuracy, coverage, Brier, log loss;
  A and C compared on identical samples and coverage; latency source.
- Reproducibility: `config_json` suffices to re-derive the run.

Quality gate: `black`, `ruff`, `pytest`; `ai-code-review` before declaring
done.

## 11. Open items

- Split sizes and N/topology confirmation: decided after the pilot (§5.4).
- Variance strategy if the pilot shows negligible variance (§5.4).
- Public-data source and licence check (later experiment).
