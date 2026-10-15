# Tasks

Source of truth for tasks. Current state and confirmed constraints live in
`CURRENT_STATE.md`. One line per card; link to detail instead of copying it.

## Next

- [ ] Experiment 1: Fixed Judges + Average — brainstorm, then spec. Jev only, on the existing `Judge`/`JevStageExecutor`, no dynamic activation. Resolve fixed baselines under A–F, the High/Low ground truth and data pipeline (`src/data/` is a stub), and Judge roles (`src/judges/definitions/`). Pin hypothesis, metrics, ablation, and logs (attempts, fetched answers, latency, coverage, calibration, `SKIP`). Keep B and D out of the simple fixed-average baseline.

## Waiting (human / external)

- [ ] Pin primary-source URLs for the decision-model abstraction input (`docs/context/djn-research-input-decision-model-abstraction.md`).

## Parked

- [ ] Dynamic provider selection and OpenAI Decisions (beta) — deferred.
- [ ] Graph, aggregation, runtime, experiments, metrics, escalation — remain stubs until Experiment 1 is specified.
