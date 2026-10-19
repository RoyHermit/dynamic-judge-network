Experiment 1 runner and offline pipeline (spec: `docs/superpowers/specs/2026-10-15-experiment-1-fixed-judges-average-design.md`).

- `runner.py`: resumable A / C execution (`batched` or `separate` replicas).
- `pilot.py`: replica-variance statistics gating the N/topology choice.
- `pipeline.py`: fit (calibrator + margins), score, persist decisions.
- `cli.py`: `run` (spends API budget, human-only), `pilot-stats`, `fit`, `report`.

Experiment 2, role decomposition (spec: `docs/superpowers/specs/2026-10-19-experiment-2-role-decomposition-design.md`;
human-run stages: `docs/superpowers/plans/exp2-runbook.md`).

- `exp2_config.py`: Exp2 settings (split sizes, Platt L2, min gain, pilot thresholds).
- `exp2_arms.py`: A' / A'x5 / D specs; `arm_spec` builds any arm, `n_expected` its answer count.
- `exp2_pilot.py`: §9 pilot stop rules (`pilot_check`).
- `exp2_pipeline.py`: Platt fit (isotonic sensitivity), freeze, score.
- `verdict.py`: §5 success rule per dataset and the §11 cross-dataset verdict.
- `exp2_report.py`, `exp2_report_sections.py`: report (arms, paired comparisons, diagnostics, verdict).
- `exp2_cli.py`: `run` (spends API budget, human-only), `pilot-check`, `fit`, `report`, `verdict`.
