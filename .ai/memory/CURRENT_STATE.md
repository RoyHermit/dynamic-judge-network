# Current State — Dynamic Judge Network

Branch: `main` (foundation work merged, fast-forward, commit `d118a69`).

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
- Full test suite: 30/30 passing (`venv/bin/pytest`), `black`/`ruff` clean.
- Research background lives in
  `docs/context/dynamic-judge-network-context.md` (read this before any
  new spec — every future spec assumes it).

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

Not started: brainstorm + spec the first Ablation Test experiment per
context doc §15 — **Experiment 1: Fixed Judges + Average** (a Baseline B
"diverse fixed ensemble" using the now-built `Judge`/`JevStageExecutor`
foundation, no dynamic activation yet). Concrete Judge implementations
(Trend, Momentum, etc., under `src/judges/definitions/`) and the
benchmark data pipeline (`src/data/`, spec §10, still just a stub) are
both prerequisites this next spec needs to resolve.

## Known open items (intentionally deferred, not blockers)

- Benchmark data pipeline (State shape, HIGH/LOW data source) — separate
  future spec (spec §10).
- Graph/aggregation/runtime/experiments/metrics/escalation are all still
  stub `README.md` files under `src/` — untouched by design (spec §10).
