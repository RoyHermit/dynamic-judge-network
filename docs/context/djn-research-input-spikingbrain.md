# DJN Research Input: SpikingBrain-Inspired Sparse Decision Mechanisms

> **Target project:** `RoyHermit/dynamic-judge-network`
>
> **Primary source:** *SpikingBrain: Spiking Brain-inspired Large
> Models*, Yuqi Pan et al., arXiv:2509.05276v4, revised 2026-05-08.
>
> **Purpose:** Research input for Claude Code, Codex, and other agents
> working on Dynamic Judge Network (DJN).
>
> **Boundary:** SpikingBrain operates inside a neural model. DJN
> operates primarily between heterogeneous Judges. This document
> extracts architectural principles and converts them into testable DJN
> hypotheses; it does not propose reproducing SpikingBrain or
> implementing an SNN.
>
> **Integration note (2026-10-02):** These are candidate later-stage
> experiments, not a change to Experiment 1. For the initial High/Low
> benchmark, critically missing input data fails the deterministic gate
> and returns `SKIP` before any Judge runs. Burst-like Judge activation
> applies only to valid but difficult inputs. The
> [core research context](dynamic-judge-network-context.md) records this
> boundary and the measurement definitions used when designing ablations.

## 1. Why this paper matters

DJN already investigates sparse activation, specialized Judges, dynamic
reasoning paths, excitation/inhibition, counter-evidence, early
stopping, compact intermediate state, and adaptive allocation of
computation.

SpikingBrain provides an architectural precedent for a broader
principle:

> **Computation does not need to be dense and uniform. Activity can be
> conditional, sparse, state-dependent, and dynamically regulated.**

DJN should test whether this principle remains useful when the unit of
activation is a **Judge**, rather than a neuron or model expert.

## 2. What SpikingBrain actually proposes

The paper describes SpikingBrain-7B and a 76B-class hybrid-linear MoE
model. Relevant mechanisms include:

-   hybrid efficient attention;
-   adaptive-threshold spiking neurons;
-   sparse spike coding;
-   Mixture-of-Experts modular specialization;
-   compressed and continuously updated state in linear attention;
-   network-level plus neuron-level sparsity.

The paper reports event-driven spiking behavior and about 69% spiking
sparsity for its scheme, together with substantial long-context
efficiency results. These are **SpikingBrain results**, not expected DJN
results.

## 3. Event-driven computation → Event-driven Judge activation

SpikingBrain converts activations into integer spike counts and sparse
spike trains. At a conceptual level, activity occurs when activation is
sufficient.

DJN abstraction:

``` text
continuous evidence
        ↓
activation accumulation
        ↓
threshold reached?
   ┌────┴────┐
   │         │
  no        yes
   │         │
dormant    Judge fires
```

Hypothesis:

> **Judges should not execute merely because they exist in the graph.
> They should execute when accumulated evidence makes their information
> valuable enough.**

This is a DJN hypothesis, not a claim made by the paper.

## 4. Adaptive Threshold

SpikingBrain uses adaptive firing thresholds to avoid both excessive
activity and excessive inactivity. The threshold responds to activation
statistics, creating an explicit accuracy--sparsity trade-off.

High-level interpretation:

``` text
strong overall activation
        ↓
threshold rises
        ↓
redundant firing reduced

weak overall activation
        ↓
threshold falls
        ↓
important weak activity retained
```

## 5. DJN hypothesis: Adaptive Judge Threshold

Instead of:

``` text
if activation_score > FIXED_THRESHOLD:
    run_judge()
```

test:

``` text
if activation_score > threshold(judge, network_state):
    run_judge()
```

The threshold could eventually depend on:

``` text
current consensus
current uncertainty
current disagreement
already collected evidence
Judge cost
Judge latency
historical information gain
current hypothesis direction
remaining compute budget
```

Example:

``` text
Current state:
HIGH evidence = strong
LOW evidence  = weak
uncertainty   = medium

additional HIGH-support Judge:
    threshold ↑

counter-HIGH Judge:
    threshold ↓

uncertainty-resolution Judge:
    threshold ↓
```

The purpose is state-dependent allocation of Judge computation, not
biological simulation.

## 6. Confirmation-cascade control

Without regulation:

``` text
Trend -> HIGH
  ↓
Momentum -> HIGH
  ↓
Breakout -> HIGH
  ↓
another supporting Judge -> HIGH
```

The network may waste compute confirming its current belief.

Proposed DJN behavior:

``` text
strong HIGH consensus
        │
        ├── HIGH-support threshold ↑
        ├── counter-HIGH threshold ↓
        └── overextension threshold ↓
```

Hypothesis:

> **As one hypothesis becomes dominant, redundant confirmation should
> become harder to activate while useful contradiction becomes easier to
> activate.**

## 7. Multi-scale sparsity → Hierarchical DJN sparsity

SpikingBrain combines network-level sparsity through MoE with
finer-grained spiking sparsity.

DJN analogy:

``` text
SpikingBrain                  DJN
--------------------------------------------------
MoE expert routing        -> Judge-group routing
expert specialization     -> Judge specialization
spike activation          -> individual Judge activation
network sparsity          -> group sparsity
neuron sparsity           -> Judge sparsity
```

This is an abstraction, not architectural equivalence.

## 8. Judge Group Selection

Possible groups:

``` text
Trend Group
Momentum Group
Risk Group
Mean-Reversion Group
Regime Group
Counter-Evidence Group
Data-Quality Group
```

Only relevant groups activate. Within them, only selected Judges fire.

``` text
Input
  ↓
Group activation
  ├── Trend Group ───────── ACTIVE
  ├── Momentum Group ────── ACTIVE
  ├── Mean-Reversion Group  dormant
  ├── Risk Group ────────── ACTIVE
  └── Counter Group ─────── ACTIVE
               ↓
        per-Judge activation
               ↓
       actual Judges executed
```

This converts a flat routing problem from "which of 100 Judges?" into
"which functional group, then which Judges?"

## 9. Compressed continuously updated state → Evidence State

SpikingBrain discusses compressed, continuously updated state in its
linear-attention design.

DJN can test an analogous recurrent reasoning state:

``` text
Raw Input
   ↓
Evidence State S0
   ↓
Activation Wave 0
   ↓
Evidence State S1
   ↓
Activation Wave 1
   ↓
Evidence State S2
   ↓
Decision
```

Conceptually:

``` text
S(t+1) = update(S(t), JudgeOutputs(t))
```

Possible Evidence State fields:

``` text
directional evidence
risk evidence
regime
data quality
consensus
disagreement
uncertainty
counter-evidence strength
activated groups
completed Judges
remaining compute budget
```

Later Judges should receive the smallest sufficient representation of
prior evidence where possible.

## 10. Evidence State requires ablation

Compression may remove useful information. Compare:

``` text
A. full raw state
B. raw state + previous Judge outputs
C. compact Evidence State
D. Evidence State + selected raw features
```

Measure:

``` text
accuracy
calibration
latency
provider input size
cost
routing quality
Judge confidence
```

Preserve raw observations in durable logs regardless of what later
Judges receive.

## 11. Functional specialization

The MoE analogy reinforces DJN's use of intentionally different Judge
roles.

Potential modules:

``` text
Trend
Momentum
Mean Reversion
Volatility
Regime
Data Quality
Counter-Evidence
Uncertainty
Risk
```

The objective is not maximum Judge count. It is useful diversity.

Measure:

``` text
individual accuracy
pairwise error correlation
unique correct decisions
conditional information gain
activation frequency
decision-changing frequency
latency
cost
```

A weaker standalone Judge may still be valuable if it catches failures
dominant Judges miss.

## 12. New metric: Judge Sparsity

Basic metric:

``` text
Judge Sparsity
    = 1 - distinct_attempted_judges / available_judges
```

Example:

``` text
available Judges            = 40
distinct attempted Judges  = 10
Judge Sparsity             = 0.75
```

This DJN operational definition counts each Judge whose question was
attempted, including failed calls, once. Log the candidate-pool version
and keep fetched, activated, and used counts separate. Retries and
provider requests remain separate resource metrics; sparsity alone is
not cost. Report gate-failed inputs separately so a no-execution `SKIP`
does not inflate the apparent benefit of a routing policy.

Do not optimize this alone. Extreme sparsity can simply mean
insufficient reasoning.

Also consider:

``` text
judge_sparsity
group_sparsity
wave_sparsity
weighted_compute_sparsity
provider_call_sparsity
```

Future weighted metric:

``` text
weighted_compute_sparsity
= 1 - actual_compute_cost / dense_compute_cost
```

## 13. Accuracy--Sparsity frontier

SpikingBrain reports an accuracy--sparsity trade-off. DJN should
explicitly measure its own analogous frontier.

The evaluation space becomes:

``` text
Accuracy
Latency
Cost
Coverage
Sparsity
```

Conceptually:

``` text
too dense
  -> unnecessary cost/latency

balanced
  -> sufficient evidence with moderate compute

too sparse
  -> information loss / accuracy loss / excessive SKIP
```

The question is whether dynamic sparse execution reaches a better Pareto
region than fixed execution.

## 14. Adaptive Compute Intensity

A strong DJN abstraction is:

``` text
easy sample
    ↓
high-confidence early evidence
    ↓
few Judges
    ↓
early stop

hard sample
    ↓
conflicting evidence
    ↓
specialists become easier to activate
    ↓
additional waves

rare / unusual sample
    ↓
important anomaly
    ↓
temporary burst of Judge activity
    ↓
many specialists or frontier fallback
```

Computation becomes input-dependent.

## 15. Burst-like reasoning

SpikingBrain preserves important rare high-magnitude activity through
stronger spike responses.

DJN hypothesis:

``` text
normal case
    -> sparse reasoning

rare / contradictory / high-risk case
    -> temporary burst of Judge activity
```

Possible triggers:

``` text
high disagreement
rare regime
out-of-distribution signal
strong counter-evidence
uncertain but gate-valid data quality
unexpected Judge conflict
```

Sparsity may intentionally decrease for difficult samples.

> **Sparsity is a resource-management mechanism, not a requirement that
> every input use minimal compute.**

## 16. Integration with Activation Waves

``` text
Input
  ↓
Deterministic Gates
  ↓
Group Activation
  ↓
Wave 0 [J1 J2 J3]
  ↓
Evidence State
  ↓
Adaptive Threshold Update
  ↓
Group / Judge Activation
  ↓
Wave 1 [J7 Counter-J]
  ↓
Evidence State
  ├── sufficient -> STOP
  └── conflict   -> Burst Wave [J9 J12 J18]
                        ↓
                     Decision
```

This preserves parallel execution inside waves while allowing
event-driven dynamic depth.

## 17. Candidate activation model

This is an experimental hypothesis, not final mathematics.

Each Judge may have:

``` text
base_threshold_j
activation_score_j
adaptive_threshold_j
cost_j
latency_j
group_j
```

Possible score:

``` text
activation_score_j =
    Σ(edge_weight_i_j * evidence_i)
    + context_bias_j
    + uncertainty_bonus_j
    + counter_evidence_bonus_j
```

Activation:

``` text
fire(j)
if activation_score_j >= adaptive_threshold_j
```

Possible threshold:

``` text
adaptive_threshold_j =
    base_threshold_j
    + redundancy_penalty
    - uncertainty_bonus
    - contradiction_bonus
    + budget_penalty
```

Interpretation:

``` text
redundant supporting evidence -> harder to activate
high uncertainty              -> specialists easier to activate
need for contradiction        -> counter-Judges easier to activate
low remaining budget          -> expensive Judges harder to activate
```

Start substantially simpler in the first PoC.

## 18. Initial implementation should remain deterministic

Example:

``` text
if consensus > 0.80:
    raise supporting_threshold

if disagreement > 0.40:
    lower uncertainty_group_threshold

if direction == HIGH and confidence > 0.65:
    lower counter_high_threshold

if evidence_sufficient and uncertainty < 0.20:
    stop
```

This is inspectable, reproducible, debuggable, and suitable for
ablation.

Learned thresholds or learned edge weights should come only after
sufficient data exists.

## 19. Threshold ablation

Add an explicit comparison:

``` text
T0 — all Judges always execute
T1 — fixed Judge activation thresholds
T2 — adaptive thresholds
T3 — adaptive thresholds + hierarchical group routing
T4 — adaptive thresholds + group routing + counter-evidence
T5 — learned threshold/routing policy
```

Compare:

``` text
accuracy
coverage
latency
cost
Judge sparsity
group sparsity
wave count
calibration
```

## 20. New research questions

### RQ-S1

Can adaptive Judge thresholds improve the accuracy--sparsity trade-off
compared with fixed thresholds?

### RQ-S2

Does hierarchical Judge-group routing outperform flat Judge routing at
comparable accuracy?

### RQ-S3

Can redundant confirmation be reduced by increasing activation
thresholds for already-supported hypotheses?

### RQ-S4

Can lowering counter-evidence thresholds reduce correlated errors?

### RQ-S5

Does compact recurrent Evidence State preserve enough information for
later activation decisions?

### RQ-S6

Do difficult or unusual samples benefit from temporary burst-like Judge
activation?

### RQ-S7

Is Judge sparsity correlated with lower latency/cost in real provider
execution, or is benefit dominated by batching/network overhead?

### RQ-S8

What is the empirical DJN accuracy--sparsity frontier?

## 21. Logging additions

Consider:

``` text
available_judge_count
available_group_count
candidate_pool_version
gate_result

requested_judges
distinct_attempted_judge_count
activated_group_count
activated_judge_count
fetched_judge_count
used_judge_count

judge_sparsity
group_sparsity

activation_score
base_threshold
adaptive_threshold

threshold_adjustment_reason
activation_reason
suppression_reason

supporting_evidence_strength
counter_evidence_strength
consensus
disagreement
uncertainty

burst_mode
burst_trigger

wave_index
wave_judge_count
wave_latency_ms

evidence_state_before
evidence_state_after

final_decision
ground_truth
```

Preserve raw values where possible and derive secondary metrics offline
when reliable.

## 22. High/Low PoC example

Candidate groups:

``` text
Directional
    Trend
    Momentum
    Breakout

Reversion
    Mean Reversion
    Overextension

Regime
    Trend Regime
    Range Regime
    Volatility

Counter-Evidence
    Counter-HIGH
    Counter-LOW

Quality
    Data Sufficiency
    Noise
```

Possible flow:

``` text
Input
  ↓
Data Quality Gate
  ↓
Wave 0:
    Trend
    Momentum
    Regime
  ↓
Evidence State:
    HIGH support strong
    trend regime likely
    uncertainty medium
  ↓
Adaptive threshold update:
    extra HIGH-support threshold ↑
    Counter-HIGH threshold ↓
    Overextension threshold ↓
  ↓
Wave 1:
    Counter-HIGH
    Overextension
  ↓
Evidence State
  ├── contradiction weak   -> HIGH
  ├── contradiction strong -> SKIP
  └── unresolved           -> additional wave
```

This tests the inspiration without implementing any spiking neural
network.

## 23. What NOT to import

Do not automatically add:

-   actual SNNs;
-   membrane-potential simulation;
-   virtual neural time steps;
-   binary/ternary spike encoding;
-   GPU kernel work;
-   neuromorphic hardware assumptions;
-   model conversion;
-   linear-attention implementation;
-   MoE training;
-   SpikingBrain's numerical threshold equation.

Those solve model-internal problems. DJN should borrow the principles,
not reproduce the implementation.

## 24. Source claims vs DJN hypotheses

### Supported by the SpikingBrain paper

``` text
adaptive-threshold spiking
event-driven sparse activity
hybrid efficient attention
MoE specialization
compressed continuously updated state
network-level + neuron-level sparsity
accuracy–sparsity trade-off
```

### Proposed by DJN based on inspiration

``` text
adaptive Judge thresholds
Judge-level event-driven activation
Judge-group hierarchical sparsity
recurrent Evidence State
confirmation suppression
counter-evidence threshold lowering
burst-like reasoning
Judge sparsity metrics
accuracy–Judge-sparsity frontier
```

The second list must not be attributed to the SpikingBrain authors.

## 25. Updated architecture candidate

``` text
                         Raw Input
                             |
                             v
                  +---------------------+
                  | Feature Computation |
                  +----------+----------+
                             |
                             v
                  +---------------------+
                  | Deterministic Gates |
                  +----------+----------+
                             |
                             v
                  +---------------------+
                  | Group Activation    |
                  +----------+----------+
                             |
                             v
                  +---------------------+
                  | Activation Wave 0   |
                  +----------+----------+
                             |
                             v
                  +---------------------+
                  |   Evidence State    |
                  +----------+----------+
                             |
                             v
                  +---------------------+
                  | Threshold Adaptation|
                  +----------+----------+
                             |
              +--------------+---------------+
              |              |               |
              v              v               v
            STOP        activate group     inhibit
                             |
                             v
                  +---------------------+
                  | Activation Wave 1   |
                  +----------+----------+
                             |
                             v
                      Evidence State
                             |
                     +-------+-------+
                     |               |
                sufficient        conflict
                     |               |
                     v               v
                  Decision       Burst Wave
                                     |
                                     v
                                  Decision
```

Treat this as an experimental architecture, not a mandatory final
design.

## 26. Updated optimization objective

``` text
quality:
    accuracy
    precision / recall
    calibration

selectivity:
    coverage
    SKIP rate

efficiency:
    latency
    provider calls
    cost

sparsity:
    Judge sparsity
    group sparsity
    weighted compute sparsity

reasoning dynamics:
    wave count
    burst rate
    early-stop rate
```

## 27. Strongest takeaway

The useful lesson is not:

> "Use spiking neurons."

It is:

> **Useful computation can be dynamically regulated so that only
> sufficiently relevant components become active, while thresholds adapt
> to preserve important information without allowing redundant activity
> to dominate.**

Translated into DJN:

> **Do not ask every Judge every question. Let accumulated evidence
> determine which specialized Judge should fire next, dynamically
> regulate activation thresholds, seek contradiction when consensus
> becomes strong, and spend more computation only on inputs that remain
> difficult.**

## 28. Recommended integration priority

``` text
After fixed-Judge baselines establish a comparator:

1. Judge Sparsity metrics
2. Fixed activation thresholds
3. Adaptive Judge thresholds
4. Counter-evidence threshold adaptation
5. Judge-group hierarchy
6. Evidence State ablation
7. Burst-like difficult-case execution
8. Learned thresholds/routing only after sufficient data
```

This keeps each mechanism experimentally attributable.

## 29. Instructions for Claude Code / Codex

1.  Do not rewrite working architecture solely to resemble SpikingBrain.
2.  Preserve Jev/provider replaceability.
3.  Treat SpikingBrain as research inspiration, not proof that DJN
    works.
4.  Add explicit hypotheses before implementation.
5.  Add metrics/logging before mechanisms that depend on those metrics.
6.  Prefer deterministic, inspectable threshold policies first.
7.  Ensure every major mechanism has a simpler baseline.
8.  Keep High/Low as the initial closed-decision benchmark.
9.  Do not introduce SNN dependencies unless a future experiment
    explicitly requires them.
10. Preserve the project rule: **Architecture follows evidence.**

## 30. Citation

Yuqi Pan et al., **"SpikingBrain: Spiking Brain-inspired Large
Models"**, arXiv:2509.05276, version 4, revised 8 May 2026.

arXiv identifier: `2509.05276`

When using quantitative claims from the paper, identify them explicitly
as SpikingBrain results rather than DJN results.
