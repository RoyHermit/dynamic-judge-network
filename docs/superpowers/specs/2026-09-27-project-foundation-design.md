# Dynamic Judge Network — Project Foundation Design

> Status: Approved (foundation scope only)
> Date: 2026-09-27
> Scope: tech stack, dependency management, directory skeleton, Judge
> interface contract, storage, testing strategy, README plan.
> Out of scope: graph/aggregation/runtime execution engine, benchmark data
> pipeline, learning phases — each gets its own spec under the Ablation Test
> plan in `docs/context/dynamic-judge-network-context.md` (§15).

## 1. Background

See `docs/context/dynamic-judge-network-context.md` for the full research
context. Summary relevant to this spec:

- The system evaluates a decision task (initial benchmark: HIGH/LOW/SKIP)
  by dynamically activating a set of lightweight "Judges" and aggregating
  their outputs.
- The initial Judge implementation candidate is **Jev**, TypeSafe AI's
  non-generative "System One" decision model. Jev answers typed questions
  (Choice / Score / Noul) against a piece of state and returns calibrated
  probabilities. It is accessed via TypeSafe's hosted API, not run locally.
- The Judge abstraction must stay provider-agnostic (§22 of the context
  doc: "Jev is replaceable") so small LLMs, classifiers, rule engines, etc.
  can be added later without changing the graph/runtime layer.

## 2. Key architectural finding: Jev speculative fan-out

Research during this session (see chat log) found that Jev's API accepts
multiple independent typed questions in a single request against one
shared state ("speculative fan-out"). Because Jev reads the state once
and scores every question against that same representation, adding
questions barely changes response time or cost — a documented cookbook
example shows 13 questions in one call being ~12x cheaper and ~10x faster
than 13 sequential calls.

Constraint: questions in the same batch are fully isolated. One
question's answer is never visible to another question in the same call.
There is no ordering effect and no cross-question conditioning.

Implication for the design in `docs/context/...`'s §8 ("critical path
depth dominates latency, not total Judge count"): Judges that belong to
the same graph stage (no dependency between them) should be batched into
a single Jev call. Judges whose activation depends on another Judge's
output (excitation/inhibition, §7.2-7.3) must live in a later, separate
call, because the batch can't see prior-in-batch answers. Cost and
latency for a Jev-backed graph are therefore driven by **stage count**
(sequential API calls), not by the number of Judges.

This finding directly shapes the Judge interface below and should be
carried into the future graph/runtime specs.

## 3. Judge interface & execution contract

A Judge does not call any API itself. It only declares a typed question
and interprets the answer. A separate executor is responsible for
batching same-stage Judges into one Jev call.

```python
class Judge(Protocol):
    def to_question(self, state: State) -> Question:
        """Declare the typed question (Choice/Score/Noul) this Judge
        wants answered against the given state. No I/O here."""
        ...

    def interpret(self, answer: Answer) -> Decision:
        """Turn Jev's typed answer into this Judge's Decision
        (direction, confidence, etc). No I/O here."""
        ...


class JevStageExecutor:
    """Collects `to_question()` output from every Judge scheduled for
    the current graph stage, sends them as ONE AsyncTypeSafeClient
    call (one state, many questions), and routes each answer back to
    the originating Judge's `interpret()`."""

    async def run_stage(self, state: State, judges: list[Judge]) -> dict[Judge, Decision]:
        ...
```

Judge implementations that are not Jev-backed (a future small-LLM or
rule-engine Judge) are not required to be batchable — they can implement
a plain `async def evaluate(state) -> Decision` instead. The graph/runtime
layer (future spec) decides per-stage whether to batch (Jev Judges) or
call independently (non-batchable Judges).

## 4. Dependencies

Core (runtime):

- `pydantic` (v2) — typed `Question` / `Answer` / `Decision` schemas,
  and config validation.
- `typesafe-sdk` — official TypeSafe Python SDK (`AsyncTypeSafeClient`).
  Handles retries/backoff on 429/529 internally.
- `python-dotenv` — loads the TypeSafe API key (and other secrets) from
  a local dotenv file that is never committed (already in `.gitignore`).

Dev/tooling:

- `black` — formatter (kept per the user's standing Python convention).
- `ruff` — lint only (imports, unused vars, style); formatting stays
  black's job to avoid two tools fighting over the same concern.
- `pytest`, `pytest-asyncio` — Judge logic and the executor are async;
  tests must not call the real Jev API (mocked per the `mock-test-data`
  skill's "no real external calls/data in tests" rule).

Package manager: `pip` + `venv`, per the user's global environment
convention (`~/.claude/CLAUDE.md`). No `uv`/`poetry`/`pip-tools` layer —
a plain `requirements.txt` is enough for a PoC of this size.

## 5. Storage

`sqlite3` (standard library, no extra dependency). Chosen over JSONL
because the project's own success criteria (§13 Metrics, §26 Success
Conditions) center on cross-experiment aggregation and Accuracy/Coverage
curves, which are far easier to compute with SQL queries/joins than by
re-parsing JSONL files per analysis.

Two tables, mapping directly onto the required log fields in
`docs/context/...` §14:

- `judge_logs`: `experiment_id, input_id, judge_id, judge_version, judge_output, judge_confidence, judge_latency, activation_source, activation_reason, graph_depth, parent_judge, timestamp`
- `decisions`: `experiment_id, input_id, aggregator_version, aggregate_score, final_confidence, final_decision, ground_truth, is_correct, total_latency, executed_judge_count, early_stopped, timestamp`

`src/storage/db.py` owns connection handling and schema creation
(idempotent `CREATE TABLE IF NOT EXISTS`). No ORM — this is a PoC; raw
SQL via `sqlite3` is simpler to read, measure, and delete later (§22
"Measure before optimize" / lean-context philosophy).

## 6. Directory skeleton (this spec's scope)

Realized now (real modules, not placeholders):

```
src/
  judges/
    interface.py       # Judge Protocol, Question/Answer/Decision (pydantic)
    jev_executor.py     # JevStageExecutor (AsyncTypeSafeClient batching)
    definitions/        # individual Judge implementations go here later
      __init__.py
  config.py             # loads secrets/config, exposes typed Settings (pydantic)
  storage/
    db.py               # sqlite connection + schema init
tests/
  test_judges/
    test_interface.py
configs/                # experiment/threshold config files (empty for now)
```

Stubbed only (empty dir + a short `README.md` stating which future spec
will fill it in — no `__init__.py` placeholders, since Python doesn't
need them to signal intent and an empty `__init__.py` communicates
nothing a `README.md` doesn't already say better):

```
src/graph/          -> README: "Graph/scheduler — see Experiment 3 spec"
src/aggregation/     -> README: "Aggregator — see Experiment 1 spec"
src/runtime/         -> README: "Execution engine — see Experiment 1 spec"
src/experiments/     -> README: "Baselines A-C, Experimental D — see Experiment 1 spec"
src/data/            -> README: "Benchmark data pipeline — separate spec, TBD"
src/metrics/         -> README: "Accuracy/latency/diversity metrics — see Experiment 1 spec"
src/escalation/      -> README: "Frontier LLM cascade — see §20, later spec"
```

## 7. Config & secrets

`src/config.py` defines a `pydantic` `Settings` model that reads the
TypeSafe API key (and future secrets) from environment variables via
`python-dotenv`. The local secrets file is already git-ignored. No secret
value is ever hard-coded or logged; `judge_logs`/`decisions` only ever
contain Judge outputs and metadata, never raw credentials.

## 8. Testing strategy

- `pytest-asyncio` for all async Judge/executor tests.
- The real Jev API is never called in tests. `JevStageExecutor` tests
  use a fake/stubbed `AsyncTypeSafeClient` returning fixture answers
  (per the `mock-test-data` skill).
- Judge `to_question`/`interpret` are pure functions and get plain
  synchronous unit tests.

## 9. README plan (English)

1. Title + one-line tagline (from context doc §28's one-sentence
   definition).
2. Link to `docs/context/dynamic-judge-network-context.md` for full
   research background — README itself stays short.
3. Architecture overview: Judge = typed question declaration; Jev
   speculative fan-out batches same-stage Judges into one API call;
   stage count (not Judge count) drives latency/cost.
4. Setup: Python 3.11+, `venv`, `pip install -r requirements.txt`,
   copy the example secrets file to your local one and fill in the
   TypeSafe API key.
5. Status: research PoC, foundation stage — links to
   `docs/superpowers/specs/` for design history.

## 10. Deferred / explicitly out of scope

- Benchmark data source/pipeline for the HIGH/LOW task.
- Graph scheduler, excitation/inhibition mechanics, early stopping.
- Aggregator implementations (average/weighted/logistic).
- Experiment runner and the Baseline A-C / Experimental D comparisons.
- Learning phases (§18).

Each will get its own brainstorming pass and spec when that Ablation
Test experiment is reached, per the project's own "One variable at a
time" principle.
