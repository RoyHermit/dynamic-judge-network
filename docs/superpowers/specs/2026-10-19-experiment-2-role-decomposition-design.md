# Experiment 2: Role-Decomposed Fixed Judges (D) — Design

Date: 2026-10-19
Status: draft for review
Builds on: `2026-10-15-experiment-1-fixed-judges-average-design.md` (pipeline,
storage, data sources, metrics) and its addenda §12-13 (first results).
Research context: `docs/context/dynamic-judge-network-context.md` §6 (Judge
diversity, error correlation) and `docs/context/djn-research-direction-update.md`
§19 (baselines A-F; this experiment implements D).

## 1. Intent

Experiment 1 showed that asking Jev the same question once (A) or five times
(C) gives the base rate, with replica errors perfectly correlated (1.0). That
was expected: C repeats one view. The original DJN idea is that **different
views fail differently**. Experiment 2 tests that, in its simplest fixed form
(baseline D): split the problem into role-specific Judges, each seeing only
the indicators of its role, and average them.

The success claim must be attributable to the decomposition, not to the mere
fact that indicators are provided; hence the control A' and the deterministic
competitors below.

## 2. Goals, non-goals, anti-goals

**Goals**
- Decide, with a preregistered test, whether D beats a single Judge that sees
  all the same indicators (A') and the other references (§5).
- Measure whether role decomposition lowers inter-Judge error correlation
  (Exp 1: 1.0) and what each role contributes.
- Reuse the Experiment 1 pipeline, storage and reporting unchanged where
  possible.

**Non-goals**
- Dynamic activation, Activation Waves, Evidence State, escalation, learned
  weights (those are B/E and later experiments).
- Prompt engineering for accuracy. Prompts are fixed before any test run.
- Provider/model comparison (single model alias, as in Exp 1).

**Anti-goals (failure even if it "works")**
- Declaring success from whichever comparator, dataset, coverage or metric
  happens to be favourable.
- Changing indicators, roles or prompts after seeing test results and reusing
  the same test split as confirmation.
- Letting any Judge see information outside its role (breaks decomposition).

## 3. Arms

All arms answer the same Noul question as Experiment 1 ("is the close
H = 5 bars after the last bar higher than the last bar's close? Answer with the
probability that it is higher") and share model alias, decoding and failure
handling. Only the *input* differs.

| Arm | Input | Calls per sample | Role |
|---|---|---|---|
| A | last 60 closes (Exp 1) | 1 | reference |
| C | last 60 closes, 5 replicas averaged (Exp 1, batched) | 1 batched | reference |
| **A'** | **all** indicators (union of D's) in one state | 1 | control: indicators without decomposition |
| A'x5 | same as A', 5 replicas averaged, separate requests | 5 | compute control for D |
| **D** | five role Judges, **each its own indicators only** | 5 (separate requests) | the hypothesis |
| D-noVol | D without the Volatility Judge | 0 extra (recomputed from D's stored answers) | prespecified ablation |

A and C must be **rerun** on the new split sizes (§7): the dataset identity
changes, so Experiment 1 answers cannot be reused.

Deterministic competitors on the same features (no LLM):

| Name | Definition |
|---|---|
| L | regularized logistic regression on the union of indicators; fitted on `calib`, regularization strength selected on `thresh`, chronologically; no new dependency (pure Python) |
| M | the momentum-sign rule of Experiment 1 (`fit_momentum`, fitted on `calib`) |
| Majority | label majority of `calib` (frozen development direction, never the test majority) |
| Const | constant probability = `calib` HIGH share |

## 4. Roles and indicators

Indicators are computed deterministically from the 60-bar window (past bars
only; no centered windows, no global scaling fitted on later data). Closes only:
ECB reference rates have no intraday high/low, so ranges use closes. A window
has 60 closes and therefore 59 one-bar log returns. Values are rounded to 4
decimals before being shown.

| Role | Indicators |
|---|---|
| Trend | OLS slope of log-close vs bar index over the 60 closes, in basis points per bar; last close relative to its 20-bar and 60-bar simple moving averages, in percent |
| Momentum | log returns over the last 5, 10 and 20 bars, in percent |
| Mean-reversion | z-score of the last close against the mean and standard deviation of the last 20 closes |
| Volatility | standard deviation of the last 10 one-bar log returns and of all 59, in percent, and their ratio |
| Breakout | position of the last close in the 20-bar range of closes, (close - low)/(high - low) |

Degenerate inputs: zero variance gives slope 0, z-score 0, volatility 0 and
ratio 1; a flat 20-bar range gives position 0.5. These are defined once in code
and tested.

A' receives all indicators in one state, with the same precision and
definitions. D's five calls each receive only their role's indicators.
Batching more than one Judge into a request is forbidden for D (a request has
one state, which would hand every Judge every role's data); D and A'x5 use
separate requests.

Prompt rule: the question sentence is identical across arms; each arm adds a
short neutral description of the indicators it is given ("You are given trend
indicators for a price series ..."). Exact wording is the builder's, fixed
before the pilot, identical for A' and D except for the role name and the
indicator list, and never tuned on `test`.

## 5. Hypothesis and preregistered success criterion

**Primary comparison: D versus A'** (the effect of decomposition).

On each dataset separately, on `test`, with accuracy at full coverage (no
`SKIP`: predict HIGH if the calibrated probability >= 0.5), using the paired
moving-block bootstrap of Experiment 1 (95% CI, same sample set):

Success on a dataset requires **all** of:
1. D - A' has a 95% CI above 0 **and** a point estimate of at least +3 percentage
   points (minimum useful improvement; builder-independent, my call).
2. D beats Majority, L and M by the same rule (CI above 0). These are an
   intersection of conditions, so no multiplicity correction is applied, but no
   claim is made from any single favourable comparison.

Reported but not part of the success rule: D vs A, C, A'x5 and Const;
D-noVol vs D; coverage-matched accuracy at 0.8; Brier and log loss (raw and
calibrated); calibration curves.

Non-significance is not evidence of equivalence. With n = 300-600 and paired
disagreement of 20-50%, the 80%-power detectable accuracy gain is roughly
6-7 points at n = 600 (7-11 at n = 300); this experiment cannot detect smaller
effects and will say so.

## 6. Diagnostics (not success criteria)

Per Judge accuracy and Brier; pairwise disagreement; inter-Judge error
correlation for D against A'x5's replica correlation. Because raw Judge
probabilities were biased low in Experiment 1 (0.14-0.37), a raw 0.5 cut would
make every error equal "label is HIGH" and the correlation trivially 1 or
undefined. So an individual Judge's error is defined **after a per-Judge Platt
calibration fitted on `calib`** (predict HIGH if calibrated p >= 0.5); the
secondary measure is the correlation of the calibrated probability residuals
(p - label). Constant error vectors are reported as undefined, never as 0. (My
call.) leave-one-out
contribution of each role to D's accuracy; D-noVol. Tokens, latency and cost per
arm (unavailable pricing stays unavailable). Lower correlation alone is not
evidence of a better ensemble (it can reflect added noise).

## 7. Data and splits

Both datasets of Experiment 1, each evaluated separately.

- Split sizes (candidates): pilot 30, calib 150, thresh 150, **test 600**,
  test_shift 300 (the largest test the ECB history can hold: about 6,700 of
  7,116 daily bars). Calibration on 150 points is noisier; see §8.
- ECB EUR/USD daily (`ecb_csv`) and synthetic (`synthetic`). Synthetic uses a
  **new seed** (not 0) so it is untouched by the Experiment 1 results.
- Experiment 1's results informed this design, so the ECB result (same file,
  shifted blocks) is **exploratory with respect to prior knowledge** and is
  labelled so; a clean confirmation needs data that do not exist yet. The
  synthetic run with a fresh seed is confirmatory for the synthetic claim.
- Primary dataset for any headline claim: **ECB** (real data); synthetic is the
  mechanism check where regimes with learnable structure exist. (My call;
  change if you disagree.)

## 8. Aggregation and calibration

- D, A'x5: mean of five valid probabilities; fewer than five valid answers
  makes the sample invalid (unchanged rule); invalid rate reported per arm.
- **Primary calibrator: Platt scaling** (two-parameter logistic on the logit
  of the mean probability), fitted on `calib`; chosen over isotonic because 150
  calibration points made isotonic overconfident in Experiment 1. Isotonic is
  reported as a sensitivity analysis. (My call.) Never refit on `test`.
- Margins for the `SKIP` analyses are chosen on `thresh` as in Experiment 1;
  the primary metric ignores `SKIP`.
- Bootstrap intervals condition on the frozen calibrator and margins; they
  omit fitting uncertainty, and the reports say so.

## 9. Execution, cost and constraints

- Jev only, `typesafe-sdk` 0.7.2, real API runs are human-authorised and
  capped; a small pilot precedes each full run.
- **Split sizes and prompts are frozen before the pilot.** The pilot may only
  stop the run or expose a definite defect (wrong units, wrong indicator,
  crash); a defect fix means the pilot is rerun, and split sizes never change
  after the pilot (a change would alter the dataset identity and discard the
  answers). Prompts are not tuned for accuracy at any point. (My call.)
- **Predeclared stop rules** (checked on the pilot, `pilot` split, 30 samples):
  stop if any arm's invalid rate exceeds 5%; if any indicator value is NaN or
  infinite; or if a Judge's probability is effectively constant (std across
  inputs below 0.01), in which case that role is reported as uninformative and
  the stop is reported rather than hidden. These thresholds are fixed now.
- **Staged runs**, each separately human-authorised: (1) pilot; (2) D and A'
  on calib, thresh, test (the primary comparison); (3) A'x5, A and C on the
  same splits; (4) `test_shift` for D, A', L, M (A'x5, A and C skipped to save
  cost; they are not needed there). (My call.)
- **`test_shift` is a secondary generalisation check**: reported next to
  `test` for D, A', L, M and Majority, never part of the success rule, and not
  used to choose anything.
- Calls per sample: A 1 + C 1 + A' 1 + A'x5 5 + D 5 = 13; about 16,000 calls
  for 1,230 samples per dataset, shorter prompts than Exp 1 (indicators, not 60
  bars); expect on the order of 5M input tokens per dataset.
- No new dependencies (logistic regression and Platt scaling in pure Python).
- Repo artifacts in English, chat in Japanese; no real data in tests (test CSV
  fixtures generated from the schema).
- One `experiment_id` per scored arm, as in Experiment 1; study ids
  `exp2` (synthetic) and `exp2-ecb`.

## 10. Left to the builder

Module layout; exact prompt wording (within §4); logistic-regression and Platt
implementation details (optimiser, regularization grid); how the runner supplies
a per-Judge state to the existing executor (one state per request); report
layout.

## 11. Combining datasets and open items

The rule for combining the two datasets is for the owner to decide (see the
review question); until decided no claim wording is fixed. The primary dataset
(§7) and the +3 point minimum useful improvement (§5) are my calls, open until
the owner confirms them; they are frozen once the plan is approved.
