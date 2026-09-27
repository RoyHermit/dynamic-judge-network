# Dynamic Judge Network — Project Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the foundation layer of Dynamic Judge Network — the
provider-agnostic Judge/executor/storage contract, a Jev-backed executor,
sqlite3 storage, config/secrets loading, the directory skeleton, and the
root README — with nothing else (graph, aggregation, runtime, experiments,
metrics, data, escalation stay stubs).

**Architecture:** One `Judge` protocol (`to_question`/`interpret`, no I/O)
is fulfilled by a `JudgeExecutor`. The only executor built here,
`JevStageExecutor`, batches every Judge in a graph stage into one
`AsyncTypeSafeClient.system_one()` call (Jev's "speculative fan-out"),
persists raw provider I/O via a `StorageWriter` the instant the provider
responds, and only then calls each Judge's `interpret()`. Storage is
plain `sqlite3` (5 tables, no ORM), written through one connection
serialized by an `asyncio.Lock`.

**Tech Stack:** Python 3.11+, `pydantic` v2, `typesafe-sdk` (verified
0.7.2 on PyPI during planning), `python-dotenv`, `pytest` +
`pytest-asyncio`, `black`, `ruff` (lint only).

**Spec:** `docs/superpowers/specs/2026-09-27-project-foundation-design.md`
(read alongside this plan — task steps below assume its §3/§5 contracts).
Background: `docs/context/dynamic-judge-network-context.md`.

**Note on verification:** every code block in this plan (interface types,
sqlite schema, storage writer, `JevStageExecutor`, and all test files) was
written to a scratch project during planning and actually run: `pytest`
(26/26 passed), `black --check`, and `ruff check` all green, against the
*real* installed `typesafe-sdk==0.7.2` package (not a guess at its shape —
its actual classes were introspected: `AsyncTypeSafeClient.system_one`,
`Choice`/`Score`/`Noul`, `ChoiceAnswer`/`ScoreAnswer`/`NoulAnswer`,
`SystemOneResponse`/`Usage`, and the `TypeSafeError` hierarchy). The code
below is exactly that verified code, not a first draft.

## Global Constraints

- Python 3.11+, `pip` + `venv` only — no `uv`/`poetry`/`pip-tools` (spec §4).
- `pydantic` v2 for every typed schema (spec §3.2, §4).
- Jev is accessed **only** through `typesafe-sdk`'s `AsyncTypeSafeClient` —
  no LiteLLM or other abstraction layer (spec §1).
- Storage is `sqlite3` (stdlib) only — no ORM (spec §5).
- `black` formats, `ruff` lints only (no formatting rules) — run both
  before every commit (spec §4, project CLAUDE.md checklist).
- `pytest` + `pytest-asyncio` for all tests; the real Jev API is never
  called in tests — fakes/stubs only (spec §8).
- `retry_count` and `token_usage` must be `None`/omitted whenever the SDK
  response doesn't actually expose the value — never fabricate or
  estimate them (spec §3, §5).
- Transaction boundaries are per **call**, not per input: `record_call()`
  (phase A) always happens before any `interpret()` call for that stage,
  and a failed provider call still gets a `calls` row (spec §3, §5).
- No secret value is ever hard-coded, logged, or committed; `.env` stays
  git-ignored (spec §7, project CLAUDE.md).
- Repo artifacts — README, docs, code, comments — are written in English;
  only chat with the user stays Japanese (project memory:
  `dynamic-judge-network-english-docs`).

## Review Focus

- **Duplicate `judge_id` across Judges passed to one `run_stage` call** —
  a naive executor would let one Judge's result silently overwrite
  another's in the returned dict; the contract requires a `ValueError`
  instead (spec §3). Pinned by `test_duplicate_judge_id_raises_value_error`
  (Task 6).
- **Provider call fails after the SDK's internal retries are exhausted** —
  an implementation that only writes on success would silently lose the
  record of a cost that was actually incurred. Pinned by
  `test_run_stage_records_error_call_on_provider_failure` (Task 6) and
  `test_failed_call_writes_calls_row_with_zero_judge_logs` (Task 4).
- **A Judge's `interpret()` raises after a successful provider call** — the
  already-recorded `calls`/`judge_logs` rows must not be rolled back or
  skipped; only that Judge's decision is absent from the result. Pinned by
  `test_interpret_raising_does_not_lose_already_recorded_call` (Task 6),
  which asserts `record_call` happens before `record_interpretation`.
- **A Noul answer with `p < 0.5`** — naively using the raw provider
  probability as `Decision.confidence` reports confidence in the wrong
  proposition (`p=0.1` must become `value=False, confidence=0.9`, not
  `confidence=0.1`). Pinned by
  `test_noul_confidence_reports_confidence_in_reported_verdict_not_raw_p`
  (Task 6).
- **Zero `judge_logs` rows for a `decisions` row** (the whole call for that
  input failed) — `COUNT(*)` over a `LEFT JOIN` wrongly counts the
  all-NULL joined row as 1 instead of 0. Pinned by
  `test_count_judge_logs_id_is_zero_not_one_for_left_join_with_no_logs`
  (Task 4).

---

## File Structure

```
requirements.txt          # pinned runtime + dev deps
pyproject.toml             # pytest config (pythonpath, asyncio_mode)
.env.example                # TYPESAFE_API_KEY placeholder, never real
README.md                   # root README (§9 plan)
src/
  config.py                 # Settings (pydantic) + python-dotenv loading
  judges/
    interface.py             # Question/Answer/Decision/Judge,
                               # CallRecord/RawJudgeRecord/StageResult,
                               # StorageWriter + JudgeExecutor protocols
    jev_executor.py           # JevStageExecutor (real typesafe_sdk types)
    definitions/
      __init__.py              # empty — concrete Judges land here later
  storage/
    db.py                     # sqlite connection + schema (5 tables)
    writer.py                  # SqliteStorageWriter (StorageWriter impl)
  graph/README.md             # stub: "see Experiment 3 spec"
  aggregation/README.md       # stub: "see Experiment 1 spec"
  runtime/README.md           # stub: "see Experiment 1 spec"
  experiments/README.md       # stub: "see Experiment 1 spec"
  data/README.md               # stub: "separate spec, TBD"
  metrics/README.md            # stub: "see Experiment 1 spec"
  escalation/README.md         # stub: "see §20, later spec"
tests/
  test_config.py
  test_judges/
    test_interface.py
    test_jev_executor.py
  test_storage/
    test_db.py
    test_writer.py
configs/
  .gitkeep                    # empty for now (spec §6); kept in git
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/judges/definitions/__init__.py`
- Create: `src/graph/README.md`, `src/aggregation/README.md`,
  `src/runtime/README.md`, `src/experiments/README.md`,
  `src/data/README.md`, `src/metrics/README.md`,
  `src/escalation/README.md`
- Create: `configs/.gitkeep`

**Interfaces:**
- Produces: a working `venv` with all deps installed; `pytest` runs
  (collects zero tests, but must not error) with `pythonpath=["."]` and
  `asyncio_mode="auto"` already configured — every later task's async
  tests rely on this so they don't need `@pytest.mark.asyncio` on each one
  (verified during planning: an unmarked `async def test_...` under
  `asyncio_mode="auto"` genuinely executes and fails on a wrong assertion,
  not a silent no-op).

- [ ] **Step 1: Create `requirements.txt`**

```
pydantic>=2,<3
typesafe-sdk>=0.7.2,<0.8
python-dotenv>=1,<2
black
ruff
pytest
pytest-asyncio
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
asyncio_mode = "auto"
```

- [ ] **Step 3: Create the venv and install dependencies**

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

Expected: install succeeds. (Verified during planning: `typesafe-sdk`
0.7.2 is the latest version on PyPI and installs cleanly with `pydantic`
2.13.x under Python 3.11+.)

- [ ] **Step 4: Verify imports and pytest config**

```bash
venv/bin/python -c "import pydantic, typesafe_sdk, dotenv, pytest, pytest_asyncio, black, ruff"
venv/bin/pytest --collect-only
```

Expected: no `ImportError`; `pytest --collect-only` reports
"no tests ran" (there are none yet) with no configuration errors.

- [ ] **Step 5: Create `.env.example`**

```
# Copy this file to .env and fill in real values. Never commit .env.
TYPESAFE_API_KEY=
```

- [ ] **Step 6: Create `src/judges/definitions/__init__.py`**

Empty file (0 bytes) — individual Judge implementations land here in a
future spec (spec §6). This is the one directory under `src/` that spec
§6 says to "realize now" as a real (if empty) package rather than a
README stub.

- [ ] **Step 7: Create the seven stub directories, each with a README.md**

Exact content per spec §6 (one line each):

`src/graph/README.md`:
```
Graph/scheduler — see Experiment 3 spec
```

`src/aggregation/README.md`:
```
Aggregator — see Experiment 1 spec
```

`src/runtime/README.md`:
```
Execution engine — see Experiment 1 spec
```

`src/experiments/README.md`:
```
Baselines A-C, Experimental D — see Experiment 1 spec
```

`src/data/README.md`:
```
Benchmark data pipeline — separate spec, TBD
```

`src/metrics/README.md`:
```
Accuracy/latency/diversity metrics — see Experiment 1 spec
```

`src/escalation/README.md`:
```
Frontier LLM cascade — see §20, later spec
```

- [ ] **Step 8: Create `configs/.gitkeep`**

Empty file. `configs/` stays empty until a future spec adds
experiment/threshold config files (spec §6); git does not track empty
directories, so this placeholder keeps the directory itself in version
control.

- [ ] **Step 9: Verify directory structure**

```bash
find src configs -type f | sort
```

Expected output (order may vary by `find` implementation, content must
match):
```
configs/.gitkeep
src/aggregation/README.md
src/data/README.md
src/escalation/README.md
src/experiments/README.md
src/graph/README.md
src/judges/definitions/__init__.py
src/metrics/README.md
src/runtime/README.md
```

- [ ] **Step 10: Commit**

```bash
git add requirements.txt pyproject.toml .env.example configs/.gitkeep \
  src/judges/definitions/__init__.py src/graph/README.md \
  src/aggregation/README.md src/runtime/README.md \
  src/experiments/README.md src/data/README.md src/metrics/README.md \
  src/escalation/README.md
git commit -m "chore: scaffold project (venv config, deps, directory skeleton)"
```

---

### Task 2: Judge/executor/storage contract types

**Files:**
- Create: `src/judges/interface.py`
- Test: `tests/test_judges/test_interface.py`

**Interfaces:**
- Consumes: nothing (pure types, no I/O).
- Produces: `Question`, `Answer`, `Decision`, `Judge` (Protocol),
  `CallRecord`, `RawJudgeRecord`, `StageResult`, `StorageWriter`
  (Protocol), `JudgeExecutor` (Protocol), `State` (= `Any`) — every later
  task imports from `src.judges.interface`.

- [ ] **Step 1: Write the failing tests**

`tests/test_judges/test_interface.py`:
```python
"""Unit tests for the Judge/executor/storage contract types.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §3.
"""

import pytest
from pydantic import ValidationError

from src.judges.interface import Answer, CallRecord, Decision, Question


def test_choice_question_requires_options():
    with pytest.raises(ValidationError):
        Question(kind="choice", prompt="pick one")


def test_choice_question_with_options_is_valid():
    question = Question(kind="choice", prompt="pick one", options=["HIGH", "LOW"])
    assert question.options == ["HIGH", "LOW"]


def test_score_question_rejects_options():
    with pytest.raises(ValidationError):
        Question(kind="score", prompt="rate it", options=["HIGH", "LOW"])


def test_noul_question_rejects_options():
    with pytest.raises(ValidationError):
        Question(kind="noul", prompt="true or false?", options=["yes"])


def test_answer_accepts_bool_raw_value_for_noul():
    answer = Answer(kind="noul", raw_value=True, raw_probability=0.9)
    assert answer.raw_value is True


def test_decision_confidence_and_evidence_are_optional():
    decision = Decision(value="HIGH")
    assert decision.confidence is None
    assert decision.evidence is None


def test_call_record_requires_status_literal():
    with pytest.raises(ValidationError):
        CallRecord(
            call_id="c1",
            experiment_id="e1",
            input_id="i1",
            stage_index=0,
            executor="JevStageExecutor",
            question_count=1,
            latency=0.1,
            status="pending",
        )


def test_judge_protocol_is_structurally_checkable():
    from src.judges.interface import Judge

    class MinimalJudge:
        judge_id = "j1"
        judge_version = "1.0"
        judge_prompt_or_definition = "minimal"

        def to_question(self, state) -> Question:
            return Question(kind="score", prompt="x")

        def interpret(self, answer: Answer) -> Decision:
            return Decision(value=answer.raw_value)

    assert isinstance(MinimalJudge(), Judge)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_judges/test_interface.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.judges'` (or
`src.judges.interface`).

- [ ] **Step 3: Write `src/judges/interface.py`**

```python
"""Provider-agnostic contracts for Judges, executors, and storage.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §3.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, model_validator

# State is deliberately unshaped at foundation scope (spec §3.2): its
# concrete structure belongs to the future benchmark data pipeline spec.
State = Any


class Question(BaseModel):
    kind: Literal["choice", "score", "noul"]
    prompt: str
    options: list[str] | None = None

    @model_validator(mode="after")
    def _options_match_kind(self) -> Question:
        if self.kind == "choice" and not self.options:
            raise ValueError("options is required when kind == 'choice'")
        if self.kind != "choice" and self.options is not None:
            raise ValueError("options must be None when kind != 'choice'")
        return self


class Answer(BaseModel):
    kind: Literal["choice", "score", "noul"]
    raw_value: str | float | bool
    raw_probability: float | None = None


class Decision(BaseModel):
    value: str | float | bool
    confidence: float | None = None
    evidence: str | None = None


@runtime_checkable
class Judge(Protocol):
    judge_id: str
    judge_version: str
    judge_prompt_or_definition: str

    def to_question(self, state: State) -> Question: ...

    def interpret(self, answer: Answer) -> Decision: ...


class CallRecord(BaseModel):
    call_id: str
    experiment_id: str
    input_id: str
    stage_index: int
    executor: str
    question_count: int
    latency: float
    retry_count: int | None = None
    token_usage: dict[str, Any] | None = None
    status: Literal["success", "error"]
    error_message: str | None = None


class RawJudgeRecord(BaseModel):
    judge_id: str
    judge_version: str
    judge_prompt_or_definition: str
    question: Question
    raw_answer: Answer
    latency: float


class StageResult(BaseModel):
    decisions: dict[str, Decision]
    calls: list[CallRecord]


@runtime_checkable
class StorageWriter(Protocol):
    async def record_call(
        self, call: CallRecord, raw_judge_records: list[RawJudgeRecord]
    ) -> None: ...

    async def record_interpretation(
        self,
        call_id: str,
        judge_id: str,
        decision: Decision | None,
        error: str | None,
    ) -> None: ...


@runtime_checkable
class JudgeExecutor(Protocol):
    async def run_stage(
        self,
        state: State,
        judges: list[Judge],
        *,
        experiment_id: str,
        input_id: str,
        stage_index: int,
    ) -> StageResult: ...
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv/bin/pytest tests/test_judges/test_interface.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Format and lint**

```bash
venv/bin/black src/judges/interface.py tests/test_judges/test_interface.py
venv/bin/ruff check src/judges/interface.py tests/test_judges/test_interface.py
```

Expected: no changes needed, no lint errors (verified during planning).

- [ ] **Step 6: Commit**

```bash
git add src/judges/interface.py tests/test_judges/test_interface.py
git commit -m "feat: add Judge/executor/storage contract types"
```

---

### Task 3: SQLite schema

**Files:**
- Create: `src/storage/db.py`
- Test: `tests/test_storage/test_db.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `connect(db_path: str | Path) -> sqlite3.Connection` — Task 4
  (`SqliteStorageWriter`) is constructed with the connection this returns.

- [ ] **Step 1: Write the failing tests**

`tests/test_storage/test_db.py`:
```python
"""Integration tests for schema creation against a real sqlite3 file.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §5.
"""

from src.storage import db


def test_connect_creates_all_five_tables(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"experiments", "inputs", "calls", "judge_logs", "decisions"} <= tables
    conn.close()


def test_connect_enables_wal_mode(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    conn.close()


def test_connect_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    db.connect(db_path).close()
    conn2 = db.connect(db_path)  # must not raise on second call
    conn2.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_storage/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.storage'`.

- [ ] **Step 3: Write `src/storage/db.py`**

```python
"""SQLite connection handling and schema initialization.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §5.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    config_json TEXT NOT NULL,
    aggregator_version TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inputs (
    input_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    input_features_json TEXT NOT NULL,
    ground_truth TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calls (
    call_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    input_id TEXT NOT NULL,
    stage_index INTEGER NOT NULL,
    executor TEXT NOT NULL,
    question_count INTEGER NOT NULL,
    latency REAL NOT NULL,
    retry_count INTEGER,
    token_usage_json TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS judge_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    input_id TEXT NOT NULL,
    judge_id TEXT NOT NULL,
    judge_version TEXT NOT NULL,
    judge_prompt_or_definition TEXT NOT NULL,
    question_json TEXT NOT NULL,
    raw_answer_json TEXT NOT NULL,
    judge_latency REAL NOT NULL,
    timestamp TEXT NOT NULL,
    interpreted_value,
    interpreted_confidence REAL,
    evidence TEXT,
    interpret_error TEXT,
    was_used INTEGER,
    activation_source TEXT,
    activation_reason TEXT,
    graph_depth INTEGER,
    parent_judge TEXT,
    UNIQUE(call_id, judge_id)
);

CREATE TABLE IF NOT EXISTS decisions (
    experiment_id TEXT NOT NULL,
    input_id TEXT NOT NULL,
    aggregate_score REAL,
    final_confidence REAL,
    final_decision TEXT,
    is_correct INTEGER,
    total_latency REAL,
    early_stopped INTEGER,
    timestamp TEXT NOT NULL,
    PRIMARY KEY (experiment_id, input_id)
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection with WAL mode enabled and ensure the schema exists.

    Safe to call repeatedly against the same file (CREATE TABLE IF NOT
    EXISTS) — this is the only place the schema is defined.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
```

Note: `interpreted_value` is declared with no type, giving it SQLite's
BLOB column affinity (no implicit conversion) — `Decision.value` can be a
`str`, `float`, or `bool`, and a `TEXT`-affinity column would silently
stringify a numeric value on write.

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv/bin/pytest tests/test_storage/test_db.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Format and lint**

```bash
venv/bin/black src/storage/db.py tests/test_storage/test_db.py
venv/bin/ruff check src/storage/db.py tests/test_storage/test_db.py
```

- [ ] **Step 6: Commit**

```bash
git add src/storage/db.py tests/test_storage/test_db.py
git commit -m "feat: add sqlite schema and connection handling"
```

---

### Task 4: StorageWriter implementation

**Files:**
- Create: `src/storage/writer.py`
- Test: `tests/test_storage/test_writer.py`

**Interfaces:**
- Consumes: `CallRecord`, `Decision`, `RawJudgeRecord` (Task 2),
  `db.connect()` (Task 3).
- Produces: `SqliteStorageWriter(conn: sqlite3.Connection)` implementing
  `StorageWriter` — Task 6 (`JevStageExecutor`) is constructed with an
  instance of this.

- [ ] **Step 1: Write the failing tests**

`tests/test_storage/test_writer.py`:
```python
"""Integration tests for SqliteStorageWriter against a real sqlite3 file.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §5, §8.
"""

import sqlite3

import pytest

from src.judges.interface import Answer, CallRecord, Decision, Question, RawJudgeRecord
from src.storage import db
from src.storage.writer import SqliteStorageWriter


def _make_call(call_id: str = "c1", status: str = "success") -> CallRecord:
    return CallRecord(
        call_id=call_id,
        experiment_id="e1",
        input_id="i1",
        stage_index=0,
        executor="JevStageExecutor",
        question_count=1,
        latency=0.05,
        retry_count=None,
        token_usage=None,
        status=status,
        error_message=None if status == "success" else "boom",
    )


def _make_raw_record(judge_id: str = "j1") -> RawJudgeRecord:
    return RawJudgeRecord(
        judge_id=judge_id,
        judge_version="1.0",
        judge_prompt_or_definition="test judge",
        question=Question(kind="choice", prompt="pick", options=["HIGH", "LOW"]),
        raw_answer=Answer(kind="choice", raw_value="HIGH", raw_probability=0.8),
        latency=0.05,
    )


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


async def test_record_call_then_interpretation_lands_in_right_columns(conn):
    writer = SqliteStorageWriter(conn)
    call = _make_call()
    await writer.record_call(call, [_make_raw_record()])
    await writer.record_interpretation(
        call_id=call.call_id,
        judge_id="j1",
        decision=Decision(value="HIGH", confidence=0.8),
        error=None,
    )

    row = conn.execute(
        "SELECT interpreted_value, interpreted_confidence, interpret_error "
        "FROM judge_logs WHERE call_id = ? AND judge_id = ?",
        (call.call_id, "j1"),
    ).fetchone()

    assert row[0] == "HIGH"
    assert row[1] == 0.8
    assert row[2] is None


async def test_record_interpretation_error_leaves_value_columns_null(conn):
    writer = SqliteStorageWriter(conn)
    call = _make_call()
    await writer.record_call(call, [_make_raw_record()])

    await writer.record_interpretation(
        call_id=call.call_id, judge_id="j1", decision=None, error="interpret blew up"
    )

    row = conn.execute(
        "SELECT interpreted_value, interpret_error FROM judge_logs WHERE call_id = ? AND judge_id = ?",
        (call.call_id, "j1"),
    ).fetchone()
    assert row[0] is None
    assert row[1] == "interpret blew up"


async def test_record_interpretation_rejects_both_decision_and_error(conn):
    writer = SqliteStorageWriter(conn)
    call = _make_call()
    await writer.record_call(call, [_make_raw_record()])

    with pytest.raises(ValueError):
        await writer.record_interpretation(
            call_id=call.call_id,
            judge_id="j1",
            decision=Decision(value="HIGH"),
            error="also this",
        )


async def test_failed_call_writes_calls_row_with_zero_judge_logs(conn):
    writer = SqliteStorageWriter(conn)
    call = _make_call(status="error")

    await writer.record_call(call, [])

    calls_row = conn.execute(
        "SELECT status, error_message FROM calls WHERE call_id = ?", (call.call_id,)
    ).fetchone()
    assert calls_row == ("error", "boom")

    logs_count = conn.execute(
        "SELECT COUNT(*) FROM judge_logs WHERE call_id = ?", (call.call_id,)
    ).fetchone()[0]
    assert logs_count == 0


async def test_count_judge_logs_id_is_zero_not_one_for_left_join_with_no_logs(conn):
    """Pins the §5 off-by-one: COUNT(*) over a LEFT JOIN counts the
    all-NULL row; COUNT(judge_logs.id) does not."""
    writer = SqliteStorageWriter(conn)
    call = _make_call(status="error")
    await writer.record_call(call, [])
    conn.execute(
        "INSERT INTO decisions (experiment_id, input_id, timestamp) VALUES (?, ?, ?)",
        ("e1", "i1", "2026-09-27T00:00:00+00:00"),
    )
    conn.commit()

    row = conn.execute(
        """
        SELECT COUNT(*) AS star_count, COUNT(judge_logs.id) AS id_count
        FROM decisions
        LEFT JOIN judge_logs
          ON judge_logs.experiment_id = decisions.experiment_id
         AND judge_logs.input_id = decisions.input_id
        WHERE decisions.experiment_id = ? AND decisions.input_id = ?
        """,
        ("e1", "i1"),
    ).fetchone()

    assert row[0] == 1  # the naive, wrong count
    assert row[1] == 0  # the correct count


async def test_unique_call_id_judge_id_prevents_duplicate_phase_a_row(conn):
    writer = SqliteStorageWriter(conn)
    call = _make_call()
    await writer.record_call(call, [_make_raw_record()])

    with pytest.raises(sqlite3.IntegrityError):
        await writer.record_call(call, [_make_raw_record()])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_storage/test_writer.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.storage.writer'`.

- [ ] **Step 3: Write `src/storage/writer.py`**

```python
"""StorageWriter implementation backed by sqlite3.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §3, §5.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone

from src.judges.interface import CallRecord, Decision, RawJudgeRecord


class SqliteStorageWriter:
    """Serializes all writes through one connection + asyncio.Lock — §5
    notes sqlite3 connections are not safe to share across concurrent
    async tasks without external serialization."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = asyncio.Lock()

    async def record_call(
        self, call: CallRecord, raw_judge_records: list[RawJudgeRecord]
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            self._conn.execute(
                """
                INSERT INTO calls (
                    call_id, experiment_id, input_id, stage_index, executor,
                    question_count, latency, retry_count, token_usage_json,
                    status, error_message, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    call.call_id,
                    call.experiment_id,
                    call.input_id,
                    call.stage_index,
                    call.executor,
                    call.question_count,
                    call.latency,
                    call.retry_count,
                    (
                        json.dumps(call.token_usage)
                        if call.token_usage is not None
                        else None
                    ),
                    call.status,
                    call.error_message,
                    now,
                ),
            )
            for record in raw_judge_records:
                self._conn.execute(
                    """
                    INSERT INTO judge_logs (
                        call_id, experiment_id, input_id, judge_id, judge_version,
                        judge_prompt_or_definition, question_json, raw_answer_json,
                        judge_latency, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        call.call_id,
                        call.experiment_id,
                        call.input_id,
                        record.judge_id,
                        record.judge_version,
                        record.judge_prompt_or_definition,
                        record.question.model_dump_json(),
                        record.raw_answer.model_dump_json(),
                        record.latency,
                        now,
                    ),
                )
            self._conn.commit()

    async def record_interpretation(
        self,
        call_id: str,
        judge_id: str,
        decision: Decision | None,
        error: str | None,
    ) -> None:
        if (decision is None) == (error is None):
            raise ValueError("exactly one of decision or error must be set")
        async with self._lock:
            self._conn.execute(
                """
                UPDATE judge_logs
                SET interpreted_value = ?,
                    interpreted_confidence = ?,
                    evidence = ?,
                    interpret_error = ?
                WHERE call_id = ? AND judge_id = ?
                """,
                (
                    decision.value if decision is not None else None,
                    decision.confidence if decision is not None else None,
                    decision.evidence if decision is not None else None,
                    error,
                    call_id,
                    judge_id,
                ),
            )
            self._conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv/bin/pytest tests/test_storage/test_writer.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Format and lint**

```bash
venv/bin/black src/storage/writer.py tests/test_storage/test_writer.py
venv/bin/ruff check src/storage/writer.py tests/test_storage/test_writer.py
```

- [ ] **Step 6: Commit**

```bash
git add src/storage/writer.py tests/test_storage/test_writer.py
git commit -m "feat: add SqliteStorageWriter"
```

---

### Task 5: Config / secrets loading

**Files:**
- Create: `src/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `TYPESAFE_API_KEY` from the environment / `.env` (via
  `python-dotenv`).
- Produces: `Settings.load() -> Settings` with `.typesafe_api_key: str` —
  the future `JevStageExecutor` wiring (not built in this plan) will read
  this to construct the real `AsyncTypeSafeClient`.

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:
```python
"""Tests for typed Settings loading. Uses MOCK_API_KEY placeholders only —
never a real secret (project CLAUDE.md security rules)."""

import pytest
from pydantic import ValidationError

from src.config import Settings


def test_settings_load_reads_api_key_from_env(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "MOCK_API_KEY")
    settings = Settings.load()
    assert settings.typesafe_api_key == "MOCK_API_KEY"


def test_settings_load_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings.load()


def test_settings_load_raises_when_api_key_empty(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "")
    with pytest.raises(ValidationError):
        Settings.load()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.config'`.

- [ ] **Step 3: Write `src/config.py`**

```python
"""Typed application settings loaded from environment variables / .env.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §7.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class Settings(BaseModel):
    typesafe_api_key: str = Field(min_length=1)

    @classmethod
    def load(cls) -> Settings:
        """Fail fast (pydantic ValidationError) if TYPESAFE_API_KEY is
        missing or empty, rather than proceeding with a falsy secret."""
        return cls(typesafe_api_key=os.environ.get("TYPESAFE_API_KEY", ""))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv/bin/pytest tests/test_config.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Format and lint**

```bash
venv/bin/black src/config.py tests/test_config.py
venv/bin/ruff check src/config.py tests/test_config.py
```

- [ ] **Step 6: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add typed Settings for TypeSafe API key loading"
```

---

### Task 6: JevStageExecutor

**Files:**
- Create: `src/judges/jev_executor.py`
- Test: `tests/test_judges/test_jev_executor.py`

**Interfaces:**
- Consumes: `Judge`, `Question`, `Answer`, `Decision`, `CallRecord`,
  `RawJudgeRecord`, `StageResult`, `StorageWriter` (Task 2); real
  `typesafe_sdk` classes (`AsyncTypeSafeClient`, `Choice`/`Score`/`Noul`,
  `ChoiceAnswer`/`ScoreAnswer`/`NoulAnswer`, `SystemOneResponse`,
  `TypeSafeError`).
- Produces: `JevStageExecutor(client, writer)` implementing
  `JudgeExecutor.run_stage(...)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_judges/test_jev_executor.py`:
```python
"""Tests for JevStageExecutor. Never calls the real Jev API — see
docs/superpowers/specs/2026-09-27-project-foundation-design.md §8."""

import pytest
import typesafe_sdk as ts

from src.judges.interface import Answer, CallRecord, Decision, Question, StageResult
from src.judges.jev_executor import JevStageExecutor


class FakeJudge:
    def __init__(self, judge_id: str, kind: str = "choice", raises: bool = False):
        self.judge_id = judge_id
        self.judge_version = "test-1.0"
        self.judge_prompt_or_definition = f"fake judge {judge_id}"
        self._kind = kind
        self._raises = raises

    def to_question(self, state) -> Question:
        if self._kind == "choice":
            return Question(
                kind="choice", prompt="HIGH or LOW?", options=["HIGH", "LOW"]
            )
        if self._kind == "score":
            return Question(kind="score", prompt="rate 0-1")
        return Question(kind="noul", prompt="is this true?")

    def interpret(self, answer: Answer) -> Decision:
        if self._raises:
            raise RuntimeError("boom")
        if answer.kind == "noul":
            p = answer.raw_probability
            value = p >= 0.5
            confidence = p if value else 1 - p
            return Decision(value=value, confidence=confidence)
        return Decision(value=answer.raw_value, confidence=answer.raw_probability)


class FakeWriter:
    def __init__(self):
        self.events: list[tuple] = []

    async def record_call(self, call, raw_judge_records):
        self.events.append(("record_call", call.call_id, call.status))

    async def record_interpretation(self, call_id, judge_id, decision, error):
        self.events.append(
            ("record_interpretation", call_id, judge_id, error is not None)
        )


class FakeClient:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error

    async def system_one(self, *, state, questions):
        if self._error is not None:
            raise self._error
        return self._response


async def test_run_stage_records_call_before_interpret():
    response = ts.SystemOneResponse(
        model="jev-1",
        usage=ts.Usage(input_tokens=10, output_tokens=0),
        answers={
            "j1": ts.ChoiceAnswer(
                choice="HIGH", confidence=0.8, probabilities={"HIGH": 0.8, "LOW": 0.2}
            )
        },
    )
    writer = FakeWriter()
    executor = JevStageExecutor(FakeClient(response=response), writer)

    result = await executor.run_stage(
        state={},
        judges=[FakeJudge("j1")],
        experiment_id="e1",
        input_id="i1",
        stage_index=0,
    )

    assert result.decisions["j1"].value == "HIGH"
    assert [e[0] for e in writer.events] == ["record_call", "record_interpretation"]


async def test_run_stage_records_error_call_on_provider_failure():
    writer = FakeWriter()
    # TypeSafeRateLimitError's real constructor needs a status/body/headers
    # triple normally built from an httpx response; the base TypeSafeError
    # is what the executor actually catches (ts.TypeSafeError), so it's
    # the honest minimal fake for "the provider call failed".
    executor = JevStageExecutor(
        FakeClient(error=ts.TypeSafeError("rate limited")), writer
    )

    result = await executor.run_stage(
        state={},
        judges=[FakeJudge("j1")],
        experiment_id="e1",
        input_id="i1",
        stage_index=0,
    )

    assert result.decisions == {}
    assert len(result.calls) == 1
    assert result.calls[0].status == "error"
    assert result.calls[0].retry_count is None
    assert writer.events == [("record_call", result.calls[0].call_id, "error")]


async def test_interpret_raising_does_not_lose_already_recorded_call():
    response = ts.SystemOneResponse(
        model="jev-1",
        usage=ts.Usage(input_tokens=10, output_tokens=0),
        answers={
            "good": ts.ChoiceAnswer(
                choice="HIGH", confidence=0.8, probabilities={"HIGH": 0.8, "LOW": 0.2}
            ),
            "bad": ts.ChoiceAnswer(
                choice="LOW", confidence=0.6, probabilities={"HIGH": 0.4, "LOW": 0.6}
            ),
        },
    )
    writer = FakeWriter()
    executor = JevStageExecutor(FakeClient(response=response), writer)
    judges = [FakeJudge("good"), FakeJudge("bad", raises=True)]

    result = await executor.run_stage(
        state={}, judges=judges, experiment_id="e1", input_id="i1", stage_index=0
    )

    assert "good" in result.decisions
    assert "bad" not in result.decisions
    call_event = next(e for e in writer.events if e[0] == "record_call")
    assert call_event[2] == "success"
    interpret_events = {
        e[2]: e[3] for e in writer.events if e[0] == "record_interpretation"
    }
    assert interpret_events == {"good": False, "bad": True}


async def test_duplicate_judge_id_raises_value_error():
    executor = JevStageExecutor(FakeClient(), FakeWriter())

    with pytest.raises(ValueError):
        await executor.run_stage(
            state={},
            judges=[FakeJudge("dup"), FakeJudge("dup")],
            experiment_id="e1",
            input_id="i1",
            stage_index=0,
        )


async def test_noul_confidence_reports_confidence_in_reported_verdict_not_raw_p():
    response = ts.SystemOneResponse(
        model="jev-1",
        usage=ts.Usage(input_tokens=5, output_tokens=0),
        answers={"j1": ts.NoulAnswer(noul=0.1)},
    )
    writer = FakeWriter()
    executor = JevStageExecutor(FakeClient(response=response), writer)

    result = await executor.run_stage(
        state={},
        judges=[FakeJudge("j1", kind="noul")],
        experiment_id="e1",
        input_id="i1",
        stage_index=0,
    )

    decision = result.decisions["j1"]
    assert decision.value is False
    assert decision.confidence == pytest.approx(0.9)


class FakeNonBatchingExecutor:
    """Test double proving StageResult.calls need not be exactly one entry
    (spec §3/§8: 'never assumed to be exactly one')."""

    def __init__(self, writer):
        self._writer = writer

    async def run_stage(self, state, judges, *, experiment_id, input_id, stage_index):
        calls: list[CallRecord] = []
        decisions: dict[str, Decision] = {}
        for judge in judges:
            question = judge.to_question(state)
            answer = Answer(kind=question.kind, raw_value="LOW", raw_probability=0.5)
            call = CallRecord(
                call_id=f"call-{judge.judge_id}",
                experiment_id=experiment_id,
                input_id=input_id,
                stage_index=stage_index,
                executor="FakeNonBatchingExecutor",
                question_count=1,
                latency=0.001,
                retry_count=None,
                token_usage=None,
                status="success",
                error_message=None,
            )
            await self._writer.record_call(call, [])
            decisions[judge.judge_id] = judge.interpret(answer)
            calls.append(call)
        return StageResult(decisions=decisions, calls=calls)


async def test_non_batching_executor_returns_one_call_record_per_judge():
    writer = FakeWriter()
    executor = FakeNonBatchingExecutor(writer)
    judges = [FakeJudge("a"), FakeJudge("b"), FakeJudge("c")]

    result = await executor.run_stage(
        state={}, judges=judges, experiment_id="e1", input_id="i1", stage_index=0
    )

    assert len(result.calls) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv/bin/pytest tests/test_judges/test_jev_executor.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.judges.jev_executor'`.

- [ ] **Step 3: Write `src/judges/jev_executor.py`**

```python
"""JudgeExecutor that batches Judges belonging to one graph stage into a
single Jev (TypeSafe System One) call — the "speculative fan-out" finding
from docs/superpowers/specs/2026-09-27-project-foundation-design.md §2.

See spec §3 for the full ordering/partial-result contract this
implements.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import typesafe_sdk as ts

from src.judges.interface import (
    Answer,
    CallRecord,
    Decision,
    Judge,
    Question,
    RawJudgeRecord,
    StageResult,
    StorageWriter,
)

_EXECUTOR_NAME = "JevStageExecutor"

_ProviderQuestion = ts.Choice | ts.Score | ts.Noul
_ProviderAnswer = ts.ChoiceAnswer | ts.ScoreAnswer | ts.NoulAnswer


def _to_provider_question(question: Question) -> _ProviderQuestion:
    if question.kind == "choice":
        assert question.options is not None  # enforced by Question itself
        return ts.Choice(
            criteria={option: None for option in question.options},
            instructions=question.prompt,
        )
    if question.kind == "score":
        # Score.criteria (scoring buckets/legend) has no DJN-side shape yet
        # (spec §3.2: State/criteria detail deferred) — empty is the
        # honest minimal translation until a future spec defines buckets.
        return ts.Score(criteria=[], instructions=question.prompt)
    return ts.Noul(instructions=question.prompt)


def _to_dj_answer(provider_answer: _ProviderAnswer) -> Answer:
    if provider_answer.type == "choice":
        return Answer(
            kind="choice",
            raw_value=provider_answer.choice,
            raw_probability=provider_answer.confidence,
        )
    if provider_answer.type == "score":
        return Answer(
            kind="score",
            raw_value=provider_answer.score,
            # ScoreAnswer.confidence is real provider data — passed through
            # raw so a Judge MAY treat it as the "actual, separately-
            # calibrated uncertainty estimate" §3.1 allows; interpret()
            # decides, this layer never fabricates or discards it.
            raw_probability=provider_answer.confidence,
        )
    # NoulAnswer only carries the raw probability — both fields are the
    # same number until interpret() applies §3.1's normalization.
    return Answer(
        kind="noul",
        raw_value=provider_answer.noul,
        raw_probability=provider_answer.noul,
    )


class JevStageExecutor:
    """A JudgeExecutor for Jev-backed Judges (spec §3)."""

    def __init__(self, client: ts.AsyncTypeSafeClient, writer: StorageWriter) -> None:
        self._client = client
        self._writer = writer

    async def run_stage(
        self,
        state: Any,
        judges: list[Judge],
        *,
        experiment_id: str,
        input_id: str,
        stage_index: int,
    ) -> StageResult:
        judge_ids = [judge.judge_id for judge in judges]
        if len(judge_ids) != len(set(judge_ids)):
            raise ValueError(f"duplicate judge_id in stage {stage_index}: {judge_ids}")

        questions = {judge.judge_id: judge.to_question(state) for judge in judges}
        call_id = str(uuid.uuid4())
        start = time.monotonic()

        try:
            response = await self._client.system_one(
                state=state,
                questions={
                    judge_id: _to_provider_question(question)
                    for judge_id, question in questions.items()
                },
            )
        except ts.TypeSafeError as exc:
            latency = time.monotonic() - start
            call = CallRecord(
                call_id=call_id,
                experiment_id=experiment_id,
                input_id=input_id,
                stage_index=stage_index,
                executor=_EXECUTOR_NAME,
                question_count=len(judges),
                latency=latency,
                retry_count=None,
                token_usage=None,
                status="error",
                error_message=str(exc),
            )
            await self._writer.record_call(call, [])
            return StageResult(decisions={}, calls=[call])

        latency = time.monotonic() - start
        token_usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        call = CallRecord(
            call_id=call_id,
            experiment_id=experiment_id,
            input_id=input_id,
            stage_index=stage_index,
            executor=_EXECUTOR_NAME,
            question_count=len(judges),
            latency=latency,
            retry_count=None,
            token_usage=token_usage,
            status="success",
            error_message=None,
        )
        raw_records = [
            RawJudgeRecord(
                judge_id=judge.judge_id,
                judge_version=judge.judge_version,
                judge_prompt_or_definition=judge.judge_prompt_or_definition,
                question=questions[judge.judge_id],
                raw_answer=_to_dj_answer(response.answers[judge.judge_id]),
                latency=latency,
            )
            for judge in judges
        ]
        await self._writer.record_call(call, raw_records)

        decisions: dict[str, Decision] = {}
        raw_by_judge_id = {record.judge_id: record for record in raw_records}
        for judge in judges:
            raw_record = raw_by_judge_id[judge.judge_id]
            try:
                decision = judge.interpret(raw_record.raw_answer)
            except Exception as exc:  # noqa: BLE001 — recorded per §3, never re-raised
                await self._writer.record_interpretation(
                    call_id=call_id,
                    judge_id=judge.judge_id,
                    decision=None,
                    error=str(exc),
                )
                continue
            await self._writer.record_interpretation(
                call_id=call_id, judge_id=judge.judge_id, decision=decision, error=None
            )
            decisions[judge.judge_id] = decision

        return StageResult(decisions=decisions, calls=[call])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv/bin/pytest tests/test_judges/test_jev_executor.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Run the full test suite**

```bash
venv/bin/pytest -v
```

Expected: 26 passed (verified during planning — this exact count/suite
ran green against the real `typesafe-sdk` package).

- [ ] **Step 6: Format and lint**

```bash
venv/bin/black src/judges/jev_executor.py tests/test_judges/test_jev_executor.py
venv/bin/ruff check src/judges/jev_executor.py tests/test_judges/test_jev_executor.py
```

- [ ] **Step 7: Commit**

```bash
git add src/judges/jev_executor.py tests/test_judges/test_jev_executor.py
git commit -m "feat: add JevStageExecutor"
```

---

### Task 7: Root README

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing consumed by other tasks.

- [ ] **Step 1: Write `README.md`**

```markdown
# Dynamic Judge Network

A bio-inspired reasoning architecture that dynamically activates diverse
lightweight evaluators, combines their competing evidence, and allocates
additional computation only when uncertainty requires it.

See [`docs/context/dynamic-judge-network-context.md`](docs/context/dynamic-judge-network-context.md)
for the full research background and hypotheses this project tests.

## Architecture

A `Judge` declares a typed question against a piece of state and
interprets a typed answer — it never performs I/O itself. Judges
belonging to the same graph stage are batched into a single Jev
("speculative fan-out") API call, since Jev reads its input state once
and scores every question against that same representation. The
project's working hypothesis — to be measured, not assumed — is that
stage count (critical path depth), not raw Judge count, dominates
latency and cost.

## Setup

Requires Python 3.11+.

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
# edit .env and set TYPESAFE_API_KEY
```

Run the tests:

```bash
venv/bin/pytest
```

## Status

Research proof-of-concept, foundation stage — the Judge/executor/storage
contract, a Jev-backed executor, and sqlite3 storage exist; the
graph/scheduler, aggregator, runtime engine, experiment runner, benchmark
data pipeline, and metrics layer are still stubs (see their `README.md`
files under `src/`). See
[`docs/superpowers/specs/`](docs/superpowers/specs/) for design history.
```

- [ ] **Step 2: Verify links resolve**

```bash
test -f docs/context/dynamic-judge-network-context.md && echo OK
test -d docs/superpowers/specs && echo OK
```

Expected: both print `OK`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add root README"
```

---

## Post-plan: update the checkpoint

After all 7 tasks are committed, update `.ai/memory/CURRENT_STATE.md`
(context-checkpoint skill) to record that the foundation implementation
is done and name whatever comes next (the first Ablation Test experiment,
per spec §10's deferred list) — do not leave the stale "not started yet"
checkpoint in place once this plan is executed.
