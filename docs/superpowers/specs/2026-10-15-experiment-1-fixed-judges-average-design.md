# Experiment 1: Fixed Judges + Average — Design

Date: 2026-10-15
Status: draft for review
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
  seam is defined), provider comparison.
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

Majority class; a deterministic momentum rule (no LLM); a regime-aware
oracle (upper bound). Needed to interpret any synthetic result.

### 4.6 Public data (later)

Same `Sample` schema, chronological date blocks, same embargo rule. A
human verifies data licensing before adoption.

## 5. Judge and execution

### 5.1 Judge definition

Noul question: "Is the close at bar t+H higher than at bar t?" `interpret`
returns `Decision.value = P(HIGH)` (the Noul probability). This avoids
averaging Choice `confidence`, which is the confidence of the *selected*
label and is not P(HIGH).

### 5.2 `Answer` extension (approved)

Add `probabilities: dict[str, float] | None = None` to `Answer`. The
executor passes the Choice probability vector through (Score keys are
stringified). Noul leaves it `None`. Stored inside `raw_answer_json`;
no schema migration.

### 5.3 Topologies

- **A**: one standalone question per request. Run twice per input to
  estimate repeat variability; never select the better run.
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
test averaging. Then choose one of (a) multiple models (`model` override;
couples with the provider axis), (b) equivalent input perturbations
(paraphrased prompt, rounded or reordered-equivalent state), or (c) drop
replication and reopen the B/D scope question. That choice is made with
the human after the pilot and recorded in an addendum to this spec.

## 6. Aggregation and decisions

1. Mean of the N replica P(HIGH) values. If fewer than N valid answers,
   the sample is **invalid** (reported as failure rate, distinct from
   SKIP); survivors are not averaged.
2. Calibrator (initial choice: isotonic) fitted on `calib` only.
3. Decision on calibrated p with margin m: `HIGH` if `p ≥ 0.5 + m`, `LOW`
   if `p ≤ 0.5 − m`, otherwise `SKIP`. Boundaries are inclusive on the
   HIGH/LOW side and defined in one place in code.
4. m is chosen on `thresh` to hit **target coverages** (e.g. 100%, 80%,
   60%), enabling matched-coverage comparison of A and C.
5. Calibrator and margins are frozen and written to `config_json` before
   `test` and `test_shift` are scored.

## 7. Metrics

- Accuracy among acted samples and coverage; risk–coverage curve;
  matched-coverage A vs C comparison.
- Brier score and log loss over all valid probabilities; reliability
  plots; per-class results.
- Paired A–C differences with block-bootstrap confidence intervals.
- Invalid-sample rate; latency percentiles; actual cost per input and per
  acted input.
- Breakdowns by regime and by `test_shift`.
- Reference baselines from §4.5.
- Latency uses `calls.latency`. `judge_logs.judge_latency` repeats the
  request latency per Judge and must never be summed.

## 8. Logging

Reuses existing tables. `config_json` additionally records: dataset and
split versions, seeds, excluded-sample counts, calibrator parameters,
margins, requested and returned model, pricing provenance, topology,
replica mapping. For A/C, requested = fetched = activated = used; the
columns (`was_used`, etc.) are still populated so E logs are comparable.

## 9. Error handling

| Event | Handling |
|---|---|
| `TypeSafeError` on a call | Keep existing behavior: `calls.status="error"`, sample invalid; no extra retry (`retry_count` stays `None`) |
| Answer dropped by SDK | Replica recorded as missing; C sample invalid |
| `interpret` raises | Existing: `interpret_error` recorded; replica invalid |
| Probability outside [0, 1] or NaN | Replica invalid; value is not clipped |
| Unlabelled sample (tie / below ε) | Excluded at generation; count recorded |
| Interrupted run | Execution idempotent per `(experiment_id, input_id, replica)`; stored triples are skipped |
| Invalid rate above 5% (configurable) | Warning at the top of the report; never silently dropped from metrics |

## 10. Testing

No real API calls; all data is generated from schemas (`mock-test-data`).

- Data: same seed → same series; `state` excludes future bars; embargo
  holds; ties/ε exclusion recorded; momentum rule ≈ 50% on random walk
  (leak/bug detector).
- Judge: `to_question`/`interpret`; `Answer.probabilities` preserved for
  Choice, `None` for Noul.
- Execution (mock Jev client): replica IDs, both topologies, missing and
  error handling, resume skips stored triples.
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
