# DJN Research Direction Update

## Jev-as-a-Judge, Decision-Layer Automation, and Staged Jev Decision Pipelines

> **Purpose:** Additional research context for AI coding agents working
> on `RoyHermit/dynamic-judge-network`.
>
> **Companion:** [Original DJN research context](dynamic-judge-network-context.md).
> This document guides future research specs where the original baseline
> taxonomy, ablation order, or logging requirements differ.
>
> **Further companion:** The
> [SpikingBrain-inspired research input](djn-research-input-spikingbrain.md)
> proposes additional, separately testable sparse-activation hypotheses
> for later work. It does not supersede this document's baseline-first
> progression or change the initial High/Low benchmark.
>
> **Status:** Research direction and proposed experimental requirements;
> the network mechanisms described below are not implemented yet.
>
> **Instruction:** Read this together with the repository's existing DJN
> context. This refines the research motivation, baselines, execution
> model, and experimental requirements. It does **not** request a
> rewrite of the existing project.

## 1. Why this update exists

Dynamic Judge Network (DJN) was originally motivated by the idea that
many lightweight, diverse evaluators could form a dynamic and sparse
decision process inspired by biological decision-making.

Subsequent review of several Jev-related approaches provides useful
prior work and concrete engineering patterns:

1.  Jev-as-a-Judge
2.  Jev in the Agent Loop / decision-layer automation
3.  Multi-question / shared-state Jev evaluation
4.  A staged Jev decision pipeline published as a practical trading-desk
    example

These sources materially influenced the refinement of DJN. They support
the broader premise that many bounded decisions do not require
open-ended generation and can instead be represented as typed,
probabilistic decision operations.

The central DJN question is:

> **Can multiple diverse lightweight Judges dynamically organize into
> sparse, multi-stage reasoning paths in which intermediate evidence
> determines what computation should happen next?**

## 2. Novelty boundary

DJN should not claim novelty for using Jev as a Judge, typed evaluation,
confidence-aware escalation, multi-question shared-state evaluation,
decision models inside agent loops, deterministic filters before model
inference, or shared-state batching.

DJN instead investigates:

-   dynamic multi-Judge composition;
-   input-dependent Judge activation;
-   sparse execution;
-   multi-stage **Activation Waves**;
-   Judge-to-Judge excitation and inhibition;
-   counter-evidence activation;
-   adaptive early stopping;
-   compact intermediate **Evidence State**;
-   later, learned routing and plasticity;
-   optimization of the accuracy--latency--cost--coverage frontier.

> **DJN does not propose using Jev as a Judge. DJN investigates whether
> intermediate judgments can dynamically determine the future reasoning
> path.**

## 3. Research lineage

``` text
Jev-as-a-Judge
      |
      | Lightweight typed models perform bounded evaluation
      v
Atomic / Multi-Rubric Judging
      |
      | Multiple narrow judgments share one state
      v
Decision-Layer Automation
      |
      | Lightweight decisions control routing/stopping
      v
Staged Decision Pipelines
      |
      | Deterministic facts, data collection and model
      | judgments form a cost-aware funnel
      v
------------------------------------------------
              DJN Research Gap
------------------------------------------------
      |
      | What if intermediate judgments determine
      | which judgments fire next?
      v
Dynamic Judge Network
      |
      +-- deterministic gates
      +-- diverse Judges
      +-- sparse activation
      +-- Activation Waves
      +-- Evidence State
      +-- excitation / inhibition
      +-- counter-evidence
      +-- early stopping
      +-- future learned paths
```

## 4. Jev-as-a-Judge implications

Jev-as-a-Judge suggests a useful decomposition:

``` text
State -> Typed Judge -> Answer + probability/confidence -> accept/reject/escalate
```

Relevant lessons:

-   a Judge can be narrow;
-   it does not need to generate prose;
-   confidence/probability can become a routing signal;
-   uncertainty can trigger additional computation;
-   multiple atomic judgments can operate over the same structured
    state;
-   stronger generative models can remain fallbacks.

DJN extends this from `one judgment -> confidence -> escalation` toward
`many local judgments -> intermediate evidence -> dynamic activation -> additional judgments only when needed`.

## 5. Decision-layer automation implications

The Jev-in-the-Agent-Loop direction separates generation from bounded
internal decisions.

``` text
Agent state -> typed decision model -> route / continue / stop / choose
```

This supports an important DJN principle:

> **Generation and decision-making should not automatically be assigned
> to the same model.**

The initial DJN PoC should nevertheless avoid a general semantic router
so that the Judge-network hypothesis remains isolated.

## 6. Lessons from the staged Jev pipeline

The reviewed practical pipeline uses a funnel approximately like:

``` text
large candidate universe
        ↓
cheap deterministic checks
        ↓
more expensive data collection
        ↓
more deterministic checks
        ↓
Jev judgments
        ↓
relative selection + absolute gate
        ↓
action / no action
```

Its useful engineering principle is:

> **Code fetches, the model judges, code decides.**

The domain-specific trading constants and strategy are not part of DJN.
The architectural separation is.

## 7. Deterministic Before Judge

Do not invoke a model for facts or arithmetic code can determine
exactly.

Bad:

``` text
Judge: Is spread > 0.5%?
Judge: Are fewer than 20 candles available?
Judge: Calculate five-minute price change.
```

Prefer computing those values in code and asking Judges uncertain
questions such as:

``` text
Is momentum likely exhausted?
Is this state consistent with continuation?
Is mean-reversion risk unusually high?
Is the evidence sufficient to act?
What contradicts the current directional hypothesis?
```

This should reduce cost and latency while improving reproducibility and
error attribution.

## 8. Deterministic Gates are network nodes

DJN should not define the network as only AI Judges. A node may be a
deterministic gate, rule, classifier, Jev Judge, small LLM, numerical
model, static analyzer, or external tool.

``` text
Input
  ↓
Deterministic Gates
  ├── invalid data -> STOP
  └── valid
        ↓
Activation Wave 0
        ↓
Evidence State
        ↓
Activation Wave 1
        ↓
Decision
```

## 9. Activation Waves

Avoid highly sequential remote execution:

``` text
J1 -> J4 -> J8 -> J12 -> Decision
```

Prefer:

``` text
Input
  ↓
Wave 0 [J1 J2 J3 J4]
  ↓
Evidence State
  ↓
routing / inhibition / stopping
  ↓
Wave 1 [J7 J9 Counter-J]
  ↓
Evidence State
  ├── sufficient -> STOP
  └── uncertain -> Wave 2 [J12 J18] -> Decision
```

Independent Judges within a wave should run concurrently. Questions
sharing state should be batched where the backend supports it and
measurement shows benefit.

> **Breadth can often be parallelized. Depth usually cannot.**

Therefore `wave_count` and `max_graph_depth` are first-class metrics.

## 10. Activation Wave as provider request boundary

A key implication of shared-state evaluation is:

``` text
Judge != API request
```

Instead of four requests that repeat the same state, one wave may send
shared state with several questions:

``` text
Wave 0:
state = shared market state
questions = trend, momentum, volatility, regime, noise
```

The controller then uses the returned evidence to construct the next
wave.

A useful implementation hypothesis is:

> **Activation Wave ≈ provider request boundary when Judges share
> state.**

This must remain an executor optimization rather than leak into the
abstract Judge API.

## 11. Fetched, Activated, and Used

Batching/speculative execution requires three separate concepts:

-   **Fetched:** provider evaluated the Judge; compute/cost was
    incurred.
-   **Activated:** the controller determined the Judge belongs to the
    reasoning path.
-   **Used:** the evidence materially affected routing, aggregation, or
    final decision.

Log these separately:

``` text
fetched_judge_count
activated_judge_count
used_judge_count
```

and preferably their identities.

## 12. Evidence State

Introduce **Evidence State** as an explicit DJN concept.

``` text
Raw State -> Wave 0 -> Evidence State -> Wave 1
```

Illustrative shape:

``` json
{
  "direction": {"trend": 0.82, "momentum": 0.71},
  "risk": {"overextension": null, "mean_reversion": null},
  "regime": "trend",
  "noise": 0.17,
  "consensus": 0.76,
  "disagreement": 0.12,
  "uncertainty": 0.21
}
```

The schema is not final. The principle is:

> **Later waves should receive the smallest sufficient representation of
> earlier evidence.**

Potential benefits to measure: reduced input size, cost and latency;
less irrelevant context; clearer routing and graph-state transitions.

## 13. Evidence State requires ablation

Compression may discard useful information. Compare:

``` text
A. Full raw state
B. Raw state + previous answers
C. Compact Evidence State
D. Evidence State + selected raw features
```

Measure accuracy, calibration, confidence, disagreement, latency and
input cost.

Raw observations must remain in durable experiment logs even if later
Judges receive compressed evidence.

## 14. Missing is not neutral

Use the rule:

``` text
missing != false
missing != safe
missing != pass
```

Missing evidence should be represented explicitly, for example as
`sufficient`, `partial`, or `insufficient`. Do not fabricate defaults
for unavailable fields.

## 15. Relative decision vs absolute gate

Separate:

``` text
Which option is best?
```

from:

``` text
Is any option good enough?
```

For High/Low this suggests separating:

``` text
Direction: HIGH / LOW
Actionability: ACT / SKIP
```

Example:

``` text
P(HIGH) = 0.64
P(actionable) = 0.31
=> SKIP
```

This is preferable to assuming a directional probability alone implies
actionability.

## 16. SKIP is first-class

Valid outcomes remain:

``` text
HIGH
LOW
SKIP
```

SKIP may result from weak evidence, Judge disagreement, missing data,
noise, strong counter-evidence, or insufficient confidence.

Evaluation should include:

``` text
coverage
accuracy_at_coverage
SKIP rate
calibration
```

## 17. Counter-evidence remains central

If the network leans HIGH:

``` text
trend -> HIGH
momentum -> HIGH
regime -> trend
```

the next useful computation may be:

``` text
overextension
mean_reversion
counter_HIGH
```

Likewise LOW may activate `counter_LOW`.

This is a concrete implementation of inhibition/adversarial evidence
seeking and should be tested for its ability to reduce correlated
errors.

## 18. Cost-aware sparse execution

Treat computation as a resource. Future node metadata may include:

``` text
expected_latency
expected_cost
historical_information_gain
activation_frequency
failure_correlation
```

Do not implement sophisticated learned scheduling initially. Start with
deterministic activation and collect evidence.

## 19. Refined baselines

### A --- Single Judge

`Input -> Judge -> Decision`

### B --- Single Judge + Confidence Escalation

Represents the Jev-as-a-Judge cascade pattern.

### C --- Fixed Multi-Judge

All selected Judges execute, followed by aggregation.

### D --- Diverse Fixed Multi-Judge

All specialist roles execute for every sample. This isolates the benefit
of diversity.

### E --- Dynamic Judge Network

Activation Waves, Evidence State, dynamic activation and early stopping.

### F --- Frontier LLM Reference

Quality/cost/latency reference; not necessarily an absolute accuracy
target.

## 20. Ablations

Suggested progression:

``` text
fixed execution
+ dynamic activation
+ Activation Waves
+ counter-evidence
+ inhibition
+ early stopping
+ Evidence State compression
+ deterministic pre-gates
+ speculative batching
+ learned routing
+ path memory / plasticity
```

Avoid introducing several mechanisms simultaneously and attributing
improvement to the whole architecture.

## 21. Logging requirements

Future logs should support reconstruction of the reasoning path:

``` text
experiment_id
sample_id
model_id
provider

wave_id
wave_index

requested_judges
fetched_judges
activated_judges
used_judges

provider_request_count
questions_per_request

network_state_before
network_state_after
evidence_state_before
evidence_state_after

activation_trigger
activation_reason
activation_score

consensus_before
consensus_after
disagreement_score
uncertainty_score

stop_evaluated
stop_result
stop_reason

provider_latency_ms
routing_latency_ms
aggregation_latency_ms
storage_latency_ms
wave_latency_ms
total_latency_ms

input_size
provider_usage

final_decision
ground_truth
```

Preserve raw provider answers separately from derived metrics.

## 22. Questions the logs must answer

Without rerunning an experiment, we should be able to ask:

-   Did Wave 2 improve accuracy?
-   How often was Wave 2 necessary?
-   Which Judge most often changed the final decision?
-   Which Judge was frequently fetched but rarely used?
-   Which Judges have correlated errors?
-   Which Judge adds unique correct predictions?
-   Does counter-evidence prevent false decisions?
-   How much latency does each wave add?
-   At what depth does marginal accuracy gain collapse?
-   Does Evidence State compression help or hurt?
-   Is speculative batching better than sparse remote execution?
-   Which activation paths are useful?
-   Which paths consume compute without improving outcomes?

## 23. High/Low remains the initial benchmark

Do not change the first benchmark:

``` text
Known single task
      ↓
Market state
      ↓
DJN
      ↓
HIGH / LOW / SKIP
```

The general semantic LLM router remains future work.

Candidate roles include Trend, Momentum, Mean Reversion, Volatility,
Breakout, Support/Resistance, Regime, Noise, Overextension,
Counter-HIGH, Counter-LOW, and Data Sufficiency.

These are candidates, not requirements. Roles should follow empirical
evidence.

## 24. Do not copy the reviewed trading strategy

The reviewed pipeline contains strategy-specific thresholds, chain
rules, social checks, position sizing, execution logic and exit logic.
These are **not** part of DJN.

Borrow only architecture-level lessons:

``` text
deterministic before probabilistic
facts before judgments
structured state
shared-state batching
explicit missing values
relative choice + absolute gate
cost-aware funneling
no-action as a valid result
durable logging
```

The DJN benchmark must define its own features, Judges, thresholds and
ground truth.

## 25. Biological inspiration

The analogy remains conceptual:

``` text
Biological principle       DJN abstraction
------------------------------------------------
sparse activation       -> only relevant Judges fire
excitation              -> evidence activates paths
inhibition              -> evidence suppresses paths
competition             -> hypotheses coexist
attention               -> compute follows evidence
early commitment        -> stop when sufficient
plasticity              -> useful paths strengthen
```

The staged funnel adds a compatible principle:

> Expensive cognitive work should occur only after cheap mechanisms
> establish that it is necessary.

The [SpikingBrain-inspired input](djn-research-input-spikingbrain.md)
suggests future comparisons of fixed versus state-adaptive Judge
thresholds, flat versus group routing, and bounded extra waves for valid
but difficult samples. These are DJN hypotheses at the Judge-network
level, not results or model-internal mechanisms transferred from the
paper. Missing critical data remains a deterministic gate failure and
produces `SKIP` before Judge execution.

## 26. Guidance for Claude Code and Codex

Preserve existing abstractions. Jev must remain replaceable and the
graph/controller should not depend directly on Jev SDK semantics.

Before implementing a mechanism, identify:

``` text
hypothesis
baseline
metric
ablation
required logs
```

Avoid premature reinforcement learning, learned topology, or neural
routing. Begin with inspectable deterministic activation.

Minimize sequential depth. Preserve raw evidence even if Evidence State
is compressed for inference. Treat no-decision as a valid result.

## 27. Suggested near-term architecture

``` text
                +---------------------+
Raw Input ----->| Feature Computation |
                +----------+----------+
                           |
                           v
                +---------------------+
                | Deterministic Gates |
                +----------+----------+
                           |
                           v
                +---------------------+
                | Activation Wave 0   |
                | J1 J2 J3 J4 ...     |
                +----------+----------+
                           |
                           v
                +---------------------+
                |   Evidence State    |
                +----------+----------+
                           |
                           v
                  Network Controller
                  /        |        \
               STOP     activate   inhibit
                          |
                          v
                +---------------------+
                | Activation Wave 1   |
                | counter/specialist  |
                +----------+----------+
                           |
                           v
                    Evidence State
                           |
                           v
                      Aggregator
                           |
                           v
                   HIGH / LOW / SKIP
```

Future versions may add learned routing, learned edge weights,
historical path memory, frontier-model escalation and a semantic task
router.

## 28. Updated core hypothesis

> **A reasoning system composed of diverse lightweight Judges,
> deterministic gates, compact intermediate evidence, dynamic activation
> waves, counter-evidence, and adaptive stopping may achieve a better
> accuracy--latency--cost--coverage trade-off than either a single
> lightweight Judge or a fixed multi-Judge ensemble.**

The strongest test is not:

``` text
Does adding more Judges improve accuracy?
```

It is:

``` text
Can the system determine
WHEN additional judgment is useful,
WHAT judgment should happen next,
and WHEN enough evidence has been collected?
```

## 29. Implementation-agent test

When considering a proposed feature, ask:

> **Does this feature help the system decide what evidence to evaluate
> next, what evidence to suppress, or when to stop evaluating?**

If yes, it is likely central to DJN.

If it merely adds another Judge that always runs, it is more likely a
baseline or specialist capability.

## 30. Final instruction

Do not maximize architectural complexity.

Preferred progression:

``` text
simple fixed baseline
        ↓
diverse fixed baseline
        ↓
simple deterministic dynamic routing
        ↓
Activation Waves
        ↓
Evidence State
        ↓
counter-evidence / inhibition
        ↓
early stopping
        ↓
measure
        ↓
only then consider learning
```

The governing rule remains:

> **Architecture follows evidence.**

The core DJN idea is:

> **What is evaluated next should depend on what has already been
> observed.**
