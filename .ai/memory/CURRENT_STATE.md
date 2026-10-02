# Current State — Dynamic Judge Network

Branch: `main` (foundation work merged; later documentation commits also
landed on `main`). Check `git rev-parse --short HEAD` for the current commit.

## Where things stand

- Project foundation design (spec) and its implementation plan are both
  approved and fully implemented on `main`:
  - Spec: `docs/superpowers/specs/2026-09-27-project-foundation-design.md`
  - Plan: `docs/superpowers/plans/2026-09-27-project-foundation.md`
- Implemented via subagent-driven-development (7 tasks + a final
  whole-branch review that caught and fixed 2 real bugs: an executor
  `KeyError` on a missing Jev answer, and a storage-writer transaction
  that wasn't rolled back on failure — see the plan file / git log for
  detail, not repeated here).
- At foundation completion, the full test suite had 30/30 passing
  (`venv/bin/pytest`) and `black`/`ruff` were clean.
- Research background lives in
  `docs/context/dynamic-judge-network-context.md` and its refinement,
  `docs/context/djn-research-direction-update.md`. The supplementary
  `docs/context/djn-research-input-spikingbrain.md` adds candidate
  later-stage hypotheses (read all three before a new research spec;
  the direction update controls where the original roadmap differs).
- The browser showcase (`index.html`, `assets/`) is a synthetic,
  dependency-free explainer of gates, waves, Evidence State, and
  `HIGH`/`LOW`/`SKIP`. The checked-in HTML embeds its assets so a single
  downloaded file works locally; regenerate it with
  `node scripts/build-showcase.mjs` after editing `assets/`. It is not
  the DJN runtime or an experiment result.

## Research direction update

- The novelty claim is dynamic composition of sparse, multi-stage Judge
  paths: intermediate evidence decides what to evaluate next and when
  to stop. Jev-as-a-Judge, typed decisions, confidence escalation,
  shared-state batching, and deterministic filtering are prior patterns.
- Plan deterministic features/gates before uncertain Judge questions.
  Keep Jev replaceable. Independent Judges may run in Activation Waves;
  shared-state batching is an executor optimization to measure, not a
  Judge API requirement.
- Treat Evidence State and `HIGH`/`LOW` direction versus `ACT`/`SKIP`
  actionability as separate experimental concepts. Missing evidence is
  explicit and never silently safe. Keep raw evidence in durable logs.
- Distinguish attempted questions, fetched answers, activated Judges,
  and used evidence. The existing DB can derive attempted/answered counts
  and has nullable `was_used`, but foundation code does not record
  activation, usage decisions, waves, or Evidence State yet.
- Use the refined baseline labels: A single Judge; B single Judge plus
  confidence escalation; C fixed multi-Judge; D diverse fixed
  multi-Judge; E dynamic DJN; F frontier LLM reference. Earlier A–E
  labels remain only in historical specs/commits. Ablate one mechanism
  at a time; do not assign later experiment numbers until their specs exist.

## SpikingBrain-inspired research input

- The paper's adaptive spiking and sparsity are model-internal findings;
  DJN's adaptive Judge thresholds, group routing, confirmation
  suppression, counter-evidence bias, and bounded bursts are untested
  network-level hypotheses. Do not transfer its numerical results or
  introduce SNN dependencies.
- Keep Experiment 1 fixed and baseline-first. Later dynamic studies can
  compare all-on, fixed-threshold, and adaptive-threshold routing. Add
  counter-threshold adjustments only after a counter-evidence baseline;
  isolate group selection and bursts. Learned policies require prior
  measurements.
- Measure distinct attempted versus activated Judge sparsity separately
  against a logged candidate pool. Keep fetched and used counts distinct.
  Report accuracy, coverage, latency, provider calls, and cost alongside
  sparsity; speculative fetches still incur work.
- Critically missing input data remains a deterministic gate failure
  returning `SKIP` before any Judge. Extra waves are candidates only for
  valid but difficult inputs.

## Confirmed decisions (do not re-litigate without new information)

- Runtime: Python 3.11+, `pip`+`venv`, no uv/poetry.
- Jev accessed via the official `typesafe-sdk` (0.7.2 verified on PyPI)
  directly — no LiteLLM layer.
- Judge interface: `to_question`/`interpret`, one contract for every
  Judge type — see spec §3 (`JudgeExecutor`, `CallRecord`, `StorageWriter`,
  phase A/B/C writes). Implemented in `src/judges/interface.py` +
  `src/judges/jev_executor.py`.
- Storage: `sqlite3` (stdlib), 5 tables — see spec §5. Implemented in
  `src/storage/db.py` + `src/storage/writer.py`.
- Tooling: `black` + `ruff` (lint only) + `pytest` + `pytest-asyncio`.
- `retry_count` is confirmed NOT exposed anywhere on `typesafe-sdk`
  0.7.2's response/error types — stays `None` permanently, not just
  until confirmed. `token_usage` (input/output tokens) IS exposed via
  `SystemOneResponse.usage` and is recorded for real.
- Repo artifacts (README, docs, code, comments) are written in English.
  Chat with the user stays Japanese — see
  `~/.claude/projects/.../memory/dynamic_judge_network_english_docs.md`.

## Next step

Not started: brainstorm + spec **Experiment 1: Fixed Judges + Average**
using the built `Judge`/`JevStageExecutor` foundation, without dynamic
activation. Resolve its exact fixed baseline comparisons under the new
A–F taxonomy, define the High/Low ground truth and benchmark data
pipeline (`src/data/`, still a stub), and specify concrete Judge roles
(`src/judges/definitions/`). Before implementation, pin down the
hypothesis, baseline, metrics, ablation, and logs, including attempts,
fetched answers, latency, coverage, calibration, and `SKIP`. The
confidence-escalation cascade (B) and diverse fixed roles (D) need
explicit experiment boundaries; do not silently bundle them into the
simple fixed-average baseline.

## Known open items (intentionally deferred, not blockers)

- Benchmark data pipeline (State shape, HIGH/LOW data source) — next
  experiment spec must resolve its interface and ground truth; it may
  warrant a separate implementation spec (foundation spec §10).
- Graph/aggregation/runtime/experiments/metrics/escalation are all still
  stub `README.md` files under `src/` — untouched by design (spec §10).
- No schema or runtime changes were made for either research input. Wave,
  Evidence State, activated/used logging, adaptive thresholds, group
  routing, bursts, and actionability semantics remain future design work.
