Experiment 1 data layer (spec: `docs/superpowers/specs/2026-10-15-experiment-1-fixed-judges-average-design.md` §4).

- `schema.py`: `Sample`, split/regime/label types, `DataSource` seam.
- `synthetic.py`: seeded generator with regime segments, ties excluded,
  embargo between chronological splits (`pilot`/`calib`/`thresh`/`test`/`test_shift`).
- `baselines.py`: majority, momentum and regime-aware reference rules.
- `windowing.py`: shared window / label / split layout (`WindowSpec`, `cut_samples`).
- `ecb.py`: public-data source reading a local ECB-style reference-rate CSV
  (`Date,USD,...`; `N/A` dropped). Splits follow time, so `test_shift` is the
  newest period. The dataset id includes the CSV content hash.
- `factory.py`: `load_source`, `dataset_identity`, `same_dataset` (picks the
  source from `data.source`: `synthetic` default, or `ecb_csv`).

The CSV is not tracked (`data/` is git-ignored). Download it yourself, check
the publisher's licence/attribution terms, and point `data.path` at it; see
`configs/exp1-ecb.example.json`.
