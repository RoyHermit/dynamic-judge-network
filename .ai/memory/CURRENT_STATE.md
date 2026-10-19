# Current State — Dynamic Judge Network

No commits to `main`; push is human-only.

## Where things stand

- Foundation spec and plan are implemented on `main`:
  `docs/superpowers/specs/2026-09-27-project-foundation-design.md`,
  `docs/superpowers/plans/2026-09-27-project-foundation.md`.
- Verified 2026-10-15: pytest 30/30; `black`/`ruff` clean. All four
  research docs and the rules import (91b317f) are on `origin/main`.
- Imported rules: `rm -rf` guard (`.ai/hooks/`), compact
  `context-checkpoint` skill, `TASKS.md` (task source of truth).
- Start research/design work at `docs/knowledge/index.md` (authority order
  and section index; read sections, not whole files). Research docs in
  `docs/context/`, read in order (direction update controls conflicts):
  `dynamic-judge-network-context.md`,
  `djn-research-direction-update.md`, `djn-research-input-spikingbrain.md`,
  `djn-research-input-decision-model-abstraction.md`.
- `index.html` + `assets/`: synthetic showcase, not the runtime
  (`node scripts/build-showcase.mjs` regenerates it).

## Research direction (details live in the docs above)

- Novelty: evidence-dependent dynamic composition of sparse multi-stage
  Judge paths. Jev-as-a-Judge, typed decisions, escalation, batching, and
  deterministic filtering are prior patterns.
- Deterministic gates first; critically missing input returns `SKIP`
  before any Judge. Evidence State, `HIGH`/`LOW`, and `ACT`/`SKIP` are
  separate concepts; attempted/fetched/activated/used counts stay
  distinct. Code does not yet record activation, usage, waves, or
  Evidence State.
- Baselines: A single; B single + escalation; C fixed multi; D diverse
  fixed multi; E dynamic DJN; F frontier LLM. Ablate one mechanism at a time.
- SpikingBrain input: adaptive thresholds, routing, bursts are untested
  hypotheses; no SNN dependencies or transferred numbers.
- Decision-model abstraction input (non-binding): Judge is a logical role,
  not a provider or request; Wave is not a provider request; keep raw
  provider output and provenance (not stored today); calibrate per
  provider on validation data only; provider axis is separate from A–F.
  Dynamic provider selection and OpenAI Decisions (beta) are deferred;
  primary-source URLs still need pinning. Showcase intentionally unchanged.

## Confirmed decisions (do not re-litigate without new information)

- Python 3.11+, `pip`+`venv`; Jev via `typesafe-sdk` 0.7.2, no LiteLLM;
  `sqlite3`, 5 tables (spec §5).
- Judge interface `to_question`/`interpret` (spec §3) lives in
  `src/judges/interface.py` and `jev_executor.py`. `JudgeExecutor` is
  broader than a provider interface; extract a provider adapter only when
  a second backend is needed.
- Tooling: `black`, `ruff` (lint only), `pytest`, `pytest-asyncio`.
- `retry_count` stays `None` (SDK); repo artifacts English, chat Japanese.

## Next step

See `TASKS.md`. Experiment 1 (A and C baselines) ran on 2026-10-19 (N=5, batched,
synthetic + ECB EUR/USD data; spec §12-13): C matches A, both at the
majority/base-rate level.
Code: branch `feat/experiment-1-fixed-judges-average`; raw results in the
git-ignored `workspace/exp1.db`. Graph, runtime, escalation remain stubs.
