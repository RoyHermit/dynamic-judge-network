Experiment 1 data layer (spec: `docs/superpowers/specs/2026-10-15-experiment-1-fixed-judges-average-design.md` §4).

- `schema.py`: `Sample`, split/regime/label types, `DataSource` seam.
- `synthetic.py`: seeded generator with regime segments, ties excluded,
  embargo between chronological splits (`pilot`/`calib`/`thresh`/`test`/`test_shift`).
- `baselines.py`: majority, momentum and regime-aware reference rules.
