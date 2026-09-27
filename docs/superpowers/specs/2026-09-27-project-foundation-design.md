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
a single Jev call. **This is a hypothesis to validate empirically in
Experiment 1/3** (RQ3), not an assumed fact — TypeSafe's own published
benchmark (13 questions ~12x cheaper/~10x faster) used a large shared
document against sequential single-question calls; this project's states
and concurrency profile are smaller and should be measured directly
before the claim is relied on.

**Activation dependency is not the same as question-content dependency.**
A downstream Judge only needs a *separate, later* Jev call if the
*wording of its question* depends on an upstream answer. If the question
itself is fixed regardless of whether the Judge ends up "activated,"
it can be asked speculatively in the same batch as everything else, and
the excitation/inhibition logic simply decides afterward whether to use
or discard that answer. Getting this distinction right is graph/runtime
scope (deferred), but the foundation layer must be able to represent it:
the storage schema below distinguishes an answer that was *fetched*
from one that was *used* (see §5), and the Judge/executor contract in
§3 does not hard-code "dependent implies separate call."

This finding directly shapes the Judge interface below and should be
carried into the future graph/runtime specs.

## 3. Judge interface & execution contract

**One contract for every Judge type, regardless of backend.** A Judge
never calls any API itself — it only declares a typed question and
interprets the typed answer. Whether that question gets answered via a
batched Jev call, a solo Jev call, a small-LLM call, or a rule engine is
entirely an *executor's* concern, not the runtime/graph layer's. This
keeps the promise in context doc §22 ("Jev is replaceable") literally
true: the graph/runtime layer only ever talks to `Judge`, never to a
Jev-specific shape.

```python
class Judge(Protocol):
    judge_id: str  # stable, unique — used as the result key (Judges are
                    # not assumed hashable/identity-stable across runs)

    def to_question(self, state: State) -> Question:
        """Declare the typed question this Judge wants answered against
        the given state. Provider-agnostic: Question is DJN's own value
        type, not Jev's wire format. No I/O here."""
        ...

    def interpret(self, answer: Answer) -> Decision:
        """Turn a typed Answer into this Judge's Decision. No I/O here."""
        ...


class CallRecord(BaseModel):
    """Telemetry for one executor invocation — maps directly onto the
    `calls` table (§5). Populated by the executor, not invented later,
    so storage never has to guess what happened inside the call."""

    question_count: int
    latency: float
    retry_count: int | None       # best-effort: only set if the SDK
                                    # response actually exposes it; a
                                    # foundation-scope executor must
                                    # leave this None rather than
                                    # fabricate a number the SDK didn't
                                    # report (see note below).
    token_usage: dict | None
    status: Literal["success", "error"]
    error_message: str | None


class StageResult(BaseModel):
    decisions: dict[str, Decision]
    call: CallRecord


class JudgeExecutor(Protocol):
    """Fulfils one or more Judges' questions for a graph stage. A
    concrete executor decides internally how (batched vs individual
    calls); callers see judge_id -> Decision PLUS the call's own
    telemetry (`StageResult`), because the runtime/storage layer needs
    the latter to write an accurate `calls` row (§5) — it cannot be
    reconstructed after the fact from decisions alone.

    Raises ValueError if `judges` contains a duplicate `judge_id` —
    silently letting one result overwrite another is never correct.

    The executor is responsible for persisting its own `CallRecord` +
    raw judge answers as soon as the provider response is in hand,
    BEFORE calling any Judge's `interpret()` — so a bug in `interpret()`
    (or in downstream code) can never cause an already-incurred provider
    call to go unrecorded. If the provider call itself fails (including
    after the SDK's internal retries are exhausted), the executor still
    persists a `CallRecord` with `status="error"` and whatever partial
    telemetry (latency, retry_count if known) is available."""

    async def run_stage(self, state: State, judges: list[Judge]) -> StageResult:
        ...


class JevStageExecutor:
    """A JudgeExecutor for Jev-backed Judges. Collects `to_question()`
    from every Judge passed in, sends them as ONE AsyncTypeSafeClient
    call (one state, many questions), and routes each Answer back to
    the originating Judge's `interpret()` via `judge_id`."""

    async def run_stage(self, state: State, judges: list[Judge]) -> StageResult:
        ...
```

**On `retry_count`:** the TypeSafe SDK documents retry *configuration*
(how many retries to attempt), not a confirmed per-response retry
*count*. Foundation-scope code must not synthesize this number if the
installed SDK version doesn't actually expose it on the response —
`retry_count = None` is the honest value in that case. Confirming
whether/how the SDK surfaces this is an implementation-time check
against the real `typesafe-sdk` package, not something this spec can
settle by reading marketing docs.

A future non-Jev Judge (small LLM, classifier, rule engine) implements
the exact same `Judge` protocol (`to_question`/`interpret`); it gets its
own `JudgeExecutor` (e.g. a `SoloLLMExecutor` that calls once per Judge,
no batching), returning the same `StageResult` shape. The graph/runtime
layer (future spec) only needs to know which executor owns which Judges
for a given stage — it never branches on Judge type.

### 3.1 `Decision` semantics across answer types

Not every Judge produces "a direction with a confidence." A Trend or
Volatility Judge's output is not inherently directional; a Jev **Noul**
answer is itself a calibrated probability, not a separate value-plus-
confidence pair. `Decision` must therefore stay a small, flexible type
rather than forcing every Judge into a `(direction, confidence)` shape:

```python
class Decision(BaseModel):
    value: str | float | bool     # meaning is Judge-defined: a Choice
                                    # label, a Score, or a Noul verdict
    confidence: float | None       # probability OF `value` specifically
                                    # (never a raw model probability of
                                    # some other fixed proposition) —
                                    # see the per-answer-type rule below
    evidence: str | None = None    # optional short rationale, if the
                                    # Judge/answer type provides one
```

`confidence` must always mean "how likely is `value` itself," which
requires a normalization step per answer type — it is not always the
raw number Jev returns:

- **Choice**: Jev already returns a probability per option. `value` =
  the chosen label, `confidence` = that label's own probability. No
  normalization needed.
- **Noul** (a yes/no support judgment for one fixed proposition): Jev
  returns `P(proposition is true)`. If that probability is `p`, the
  Judge's `interpret()` must set `value = (p >= 0.5)` and
  `confidence = p if value else 1 - p` — i.e. confidence in the
  *reported verdict*, not the raw `p`. A raw `p = 0.1` becomes
  `value = False, confidence = 0.9`, not `confidence = 0.1`.
- **Score**: a numeric score is not itself a probability. `confidence`
  is `None` unless the Judge has an actual, separately-calibrated
  uncertainty estimate to report — never synthesized from the score.

How a given Judge's `Decision.value` maps to "supports HIGH" / "supports
LOW" is aggregation-layer semantics and stays out of scope here (§10).

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

Five tables, covering every field the research context requires in §14
(the first pass of this spec missed several, and the second pass missed
call/batch tracking — both corrected per review):

- `experiments`: `experiment_id (PK), config_json, aggregator_version, created_at`
  — one immutable row per run's configuration, so `judge_logs`/`decisions`
  don't need to repeat run-level config on every row.
- `inputs`: `input_id (PK), task_type, input_features_json, ground_truth, created_at`
  — one row per benchmark input, referenced by `judge_logs`/`decisions`
  instead of duplicating features per Judge row.
- `calls`: `call_id (PK), experiment_id, input_id, stage_index, executor, question_count, latency, retry_count, token_usage_json, status, error_message, timestamp`
  — one row per actual executor invocation (one Jev batch call, or one
  solo call for a non-batching executor), written from `CallRecord`
  (§3) as soon as the provider responds — success or error — never
  deferred until the whole stage/input finishes. `retry_count` matters
  because the SDK retries 429/529 internally (§4) — one `calls` row
  does not imply exactly one provider HTTP request; it may be `NULL`
  if the SDK doesn't expose it (§3). `token_usage_json` is required to
  test the *cost* half of §2's hypothesis; `question_count`/`latency`
  alone only cover the *latency* half. `status`/`error_message` record
  invocations where the provider call itself failed (after retries were
  exhausted) — these still get a row, because the cost/attempt happened
  regardless of outcome.
- `judge_logs`: `id (PK), call_id, experiment_id, input_id, judge_id, judge_version, judge_prompt_or_definition, question_json, judge_output, judge_confidence, judge_latency, activation_source, activation_reason, graph_depth, parent_judge, was_used, timestamp`
  — every row here represents a Judge answer that was actually fetched
  (i.e. cost money/time), whether or not it was later used; `call_id`
  ties it to the batch it was fetched in, and `question_json` records
  the actual generated question (wording can vary run to run). `was_used`
  is a separate, purely semantic flag: did the graph act on this answer.
  `executed_judge_count` on `decisions` (below) MUST be defined as
  "count of `judge_logs` rows for this decision," not "count where
  `was_used`" — the former is the true execution/cost count, the latter
  is a graph-behavior metric (`used_judge_count`, computed the same way
  filtered on `was_used`, not a stored column).
- `decisions`: `experiment_id (PK, with input_id), input_id, aggregate_score, final_confidence, final_decision, is_correct, total_latency, early_stopped, timestamp`
  — `ground_truth` lives on `inputs` (not duplicated here); `is_correct`
  is derived and stored for query convenience; `executed_judge_count`
  and `used_judge_count` are computed from `judge_logs` at query time as
  `COUNT(judge_logs.id)` / `COUNT(judge_logs.id) FILTER(WHERE was_used)`
  — **`COUNT(judge_logs.id)`, never bare `COUNT(*)`**: a `LEFT JOIN`
  from `decisions` to `judge_logs` for a decision with zero logs yields
  one joined row with all-NULL `judge_logs` columns, and `COUNT(*)`
  would wrongly count that as 1 instead of 0.

`src/storage/db.py` owns connection handling and schema creation
(idempotent `CREATE TABLE IF NOT EXISTS`). No ORM — this is a PoC; raw
SQL via `sqlite3` is simpler to read, measure, and delete later (§22
"Measure before optimize" / lean-context philosophy).

**Concurrency and atomicity:** `sqlite3`'s default connection is not
safe to share across concurrent async tasks. Writes go through a single
dedicated writer (one connection, opened in WAL mode, all writes
serialized through an `asyncio.Lock` or a single writer task consuming
a queue). Reads (for analysis) can open their own short-lived read
connections.

Transaction boundaries are per *call*, not per *input*: the executor
writes its `calls` row plus the raw `judge_logs` rows **as soon as the
provider responds** — before any Judge's `interpret()` runs (§3) — so a
bug in `interpret()`, or any later graph-level failure, cannot lose the
record of a cost that was already incurred. This applies symmetrically
to success and failure: a provider call that ultimately errors out
(after the SDK's internal retries) still gets a `calls` row with
`status="error"` (§5), written at the point of failure, not skipped.
The final `decisions` row is written in its own, separate transaction
once the input's whole pipeline completes. An input that crashes
mid-processing therefore has a durable, accurate `calls`/`judge_logs`
trail (successes and failures alike) but no `decisions` row — which
correctly reflects reality (money/time were spent, no final decision
was produced) — rather than one all-or-nothing transaction that would
silently discard already-incurred cost on any later failure.

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
- Explicit storage/executor test cases (§5): a `decisions` row with
  zero associated `judge_logs` rows must report `executed_judge_count
  == 0` (guards the `COUNT(judge_logs.id)` vs `COUNT(*)` distinction);
  a stubbed executor that raises after "using up" its retries must
  still result in a persisted `calls` row with `status="error"`.

## 9. README plan (English)

1. Title + one-line tagline (from context doc §28's one-sentence
   definition).
2. Link to `docs/context/dynamic-judge-network-context.md` for full
   research background — README itself stays short.
3. Architecture overview: Judge = typed question declaration; Jev
   speculative fan-out batches same-stage Judges into one API call;
   the project's working hypothesis (to be measured, not assumed) is
   that stage count drives latency/cost more than raw Judge count.
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
