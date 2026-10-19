Experiment 1 runner and offline pipeline (spec: `docs/superpowers/specs/2026-10-15-experiment-1-fixed-judges-average-design.md`).

- `runner.py`: resumable A / C execution (`batched` or `separate` replicas).
- `pilot.py`: replica-variance statistics gating the N/topology choice.
- `pipeline.py`: fit (calibrator + margins), score, persist decisions.
- `cli.py`: `run` (spends API budget, human-only), `pilot-stats`, `report`.
