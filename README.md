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
