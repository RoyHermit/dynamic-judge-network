# Current State — Dynamic Judge Network

Branch: `docs/project-foundation-design` (NOT main — 10 commits, unpushed)

## Where things stand

- Guardrail template (claude-team-template) is installed and merged to
  `main` already (commit `0186df6`).
- Project foundation design is approved: see
  `docs/superpowers/specs/2026-09-27-project-foundation-design.md`.
  It went through 10 rounds of `codex exec` review (all findings
  addressed inline in the spec's commit history on this branch) and
  the final round returned `VERDICT: APPROVED`.
- Research background lives in
  `docs/context/dynamic-judge-network-context.md` (read this before
  the spec — the spec assumes it).

## Confirmed decisions (do not re-litigate without new information)

- Runtime: Python 3.11+, `pip`+`venv`, no uv/poetry.
- Jev accessed via the official `typesafe-sdk` directly (no LiteLLM
  layer).
- Judge interface: `to_question`/`interpret`, one contract for every
  Judge type — see spec §3 for the full executor/storage contract
  (`JudgeExecutor`, `CallRecord`, `StorageWriter`, phase A/B/C writes).
- Storage: `sqlite3` (stdlib), 5 tables — see spec §5.
- Tooling: `black` + `ruff`(lint only) + `pytest` + `pytest-asyncio`.
- **Repo artifacts (README, docs, code, comments) are written in
  English.** Chat with the user stays Japanese — see
  `~/.claude/projects/.../memory/dynamic_judge_network_english_docs.md`.

## Next step

Not started yet: invoke the `writing-plans` skill against the approved
spec to produce an implementation plan for the foundation scope
(§6 directory skeleton, Judge interface, storage, tests, README).

## Known open items (intentionally deferred, not blockers)

- Whether `typesafe-sdk` actually exposes per-call `retry_count`/token
  usage is unconfirmed — spec says do not fabricate these if absent
  (§3, §5).
- Benchmark data pipeline (State shape, HIGH/LOW data source) is a
  separate future spec (§10).
