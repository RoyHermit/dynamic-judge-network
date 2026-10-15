# DJN Research Input: Decision Model Abstraction

> **Status:** Supplementary research input, recorded 2026-10-15. It lists
> *candidate* later-stage hypotheses and design constraints. It does **not**
> override the confirmed foundation contracts, the refined baseline labels
> (A–F), or the planned order of experiments. Experiment 1 stays
> baseline-first and uses Jev only. Read this after
> `dynamic-judge-network-context.md`, `djn-research-direction-update.md`, and
> `djn-research-input-spikingbrain.md`; where they differ, the direction
> update controls.

## 1. Why this input exists

DJN started from experiments with Jev as a fast Judge. In 2026 other
providers entered the bounded-decision space, so the architecture should not
be described as "many Jev calls". Jev stays as the historical origin, the
first provider, and a baseline.

**Boundary:** DJN does not research how to build one decision model. It
researches whether many lightweight, possibly heterogeneous evaluators can
form sparse, multi-stage, evidence-dependent paths with a better
quality-latency-cost-coverage trade-off than fixed pipelines.

## 2. External context (verified 2026-10-15, secondary sources)

- **Cloudflare Clef / Clef-flash** (released 2026-10-01): decision models
  with open weights (Apache 2.0), hosted on Workers AI, described as
  Jev-API compatible. Benchmark figures are Cloudflare's own and not
  independently reproduced; latency figures differ between sources.
- **OpenAI Decisions API** (announced 2026-09-29, public beta 2026-10-06):
  `/v1/decisions`, finite answer sets, text and image input. No independent
  latency benchmarks yet; general availability is pending.
- Not verified here: Google discriminative-model framing, Clef context
  length and modality details.

These facts show an emerging provider ecosystem. They do not show identical
architectures, calibration, latency, or decision semantics; those must be
measured. Pin primary-source URLs before any claim is used in a paper.

## 3. Separations to preserve

| Concept | Meaning | Not the same as |
|---|---|---|
| Judge | Logical evaluative role in the reasoning graph | model, provider, API call |
| Provider / backend | Computation that answers a Judge's question | the Judge |
| Activation Wave | Causal reasoning stage | a provider request |
| Provider request | Execution grouping chosen by a planner | a Wave |
| Routing / stopping | What to evaluate next, when evidence suffices | provider choice |

A Wave may span several provider requests, and one request may carry several
Judges of the same Wave. A request should not carry future-wave questions
whose existence depends on current-wave evidence.

## 4. Raw output and provenance (future requirement)

Current code stores the chosen value and one converted probability; it does
not keep arbitrary raw provider payloads, full probability distributions, or
provider/model/version fields. Treat the following as a **future logging
requirement**, not as existing behavior:

- Keep raw provider output alongside normalized fields (answer, confidence).
- Record per evidence item: Judge, provider, model/version, request, state
  version, wave, timestamp.
- Keep Evidence State provider-independent (semantic direction and
  confidence plus provenance); do not spread provider schemas through DJN.

## 5. No fake equivalence; calibration is provider-specific

A 0.8 from different providers (or from a rule classifier) need not mean the
same thing. Confidence drives activation, stopping, escalation, and `SKIP`,
so calibration is part of the experiment:

- Use a common problem definition and answer space across providers.
- Fit any calibration (Platt, isotonic, temperature) on training/validation
  data only.
- Compare providers at matched coverage, not at raw confidence.
- Test whether the "same" logical Judge keeps its meaning across providers
  (semantic drift) before pooling results.

## 6. Batching versus sparsity

If one request can cheaply answer many questions, Judge-level sparsity may
not reduce real cost. Sparsity has several granularities: Judge, group,
Wave, provider request, model compute. The useful granularity may differ per
provider.

- Log `questions_per_request`, state tokens per request, provider request
  count, logical / fetched / used Judge counts, and the derived
  logical- and useful-Judges-per-request.
- Optimize measured end-to-end cost and latency, not theoretical Judge count.
- Speculative prefetch is allowed as a separate ablation (see
  `djn-research-direction-update.md`): when the same-input question set is
  fixed, fetched versus activated/used can be compared. It is **not**
  equivalent to dynamic activation when earlier evidence changes which
  questions are asked.

## 7. Separating architecture effect from provider effect

"Dynamic + Clef-flash beats Fixed + Jev" proves nothing about dynamic
routing, because two things changed. Later studies need the crossed design
(fixed/dynamic × provider) to estimate provider, architecture, and
interaction effects. Not all cells are required in one experiment.

The provider axis is **separate** from the A–F baseline labels. A candidate
provider axis, to be refined when a spec exists:

- Deterministic/rule-only; Jev; Clef-flash; Clef; OpenAI Decisions;
  frontier LLM; mixed providers (much later).

Mixing "which provider", "which model size", and "how providers are mixed"
in one list is a known weakness; split them in the spec. A deterministic
gate that returns `SKIP` before any Judge is not a "tier 0" compute tier;
compute-tier escalation overlaps baseline B and should be treated as such.

## 8. Candidate research questions

- **RQ-P1** Does the dynamic-routing benefit persist across providers?
- **RQ-P2** How much variance is provider choice versus DJN architecture?
- **RQ-P3** Best accuracy-latency-cost trade-off per Judge family and provider?
- **RQ-P4** Does a smaller/faster model become competitive with dynamic
  escalation?
- **RQ-P5 / P6** At which granularity does sparsity save real cost, and how
  does batching change the value of Judge-level sparsity?
- **RQ-P7** Can local open-weight decision models cut latency/cost without
  unacceptable accuracy loss?
- **RQ-P8** Can heterogeneous provider selection beat single-provider DJN?
- **RQ-P9 / P10** How stable is provider calibration across regimes, and
  does a logical Judge transfer across providers without semantic drift?

## 9. Candidate metrics additions

provider, model, model_version, provider_request_count,
questions_per_request, provider_latency_ms, network_latency_ms, provider
input/output units and cost, provider failure and fallback
(requested vs actual provider, fallback reason), raw and calibrated
confidence, Judge-to-provider mapping. Analyze fallback samples separately.
Continue the existing accuracy, Brier, calibration, coverage, `SKIP` rate,
wave count, sparsity, latency, and cost metrics.

## 10. Candidate sequence (not binding)

1. Finish Experiment 1 with Jev only (unchanged).
2. If a second backend is needed, extract a provider adapter from
   `JevStageExecutor`. The current `JudgeExecutor` also builds questions,
   calls the provider, stores records, and interprets answers, so it is
   broader than a provider interface; a rename alone is not enough.
3. Add a Clef/Clef-flash adapter and a provider-neutral single-Judge
   benchmark before choosing any default provider.
4. Repeat fixed multi-Judge and dynamic comparisons per provider.
5. Add OpenAI Decisions after it leaves beta and its API is stable.
6. Evaluate local open-weight execution; only later test dynamic provider
   selection.

## 11. Novelty boundary

Not novel: bounded decision models, typed decision questions, probabilistic
classification, decision APIs, model routing, and MoE routing in general.
Potential contribution stays: evidence-dependent dynamic sparse multi-stage
Judge paths, Activation Waves, Evidence State, adaptive thresholds,
counter-evidence activation, adaptive stopping, and provider-controlled
evaluation of these mechanisms. DJN is framed as an orchestration
architecture for adaptive evidence acquisition, not as a better way to use
Jev or a wrapper around decision models.

## 12. Documentation migration guidance

In architecture text, "Jev Judge" becomes "Judge"; "Jev call" becomes
"Judge evaluation" or "provider request" depending on meaning; "Jev output"
becomes "JudgeResult". Keep "Jev" for the historical origin, the specific
baseline, and Jev-specific behavior. Do not erase project history.

## 13. Sources (secondary; confirm primary announcements before citing)

- classmethod, "What is Cloudflare's Clef?":
  https://dev.classmethod.jp/en/articles/cloudflare-clef-overview/
- Developers Digest, Clef decision models:
  https://www.developersdigest.tech/blog/cloudflare-clef-decision-models-2026
- ProPakistani, OpenAI Decisions API:
  https://propakistani.pk/2026/10/07/openai-launches-decisions-api-with-up-to-10x-faster-responses/
- Dealroom, OpenAI Decisions API opens to developers:
  https://app.dealroom.co/news/note/openai-opens-decisions-api-to-all-developers-adding-image-input-in-challenge-to-typesafe-s-jev
