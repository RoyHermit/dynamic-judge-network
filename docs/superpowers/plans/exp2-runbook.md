# Experiment 2 runbook (human-run stages)

Spec: `docs/superpowers/specs/2026-10-19-experiment-2-role-decomposition-design.md`
(§9 staging and call counts, §11 verdict). Plan:
`docs/superpowers/plans/2026-10-19-experiment-2-role-decomposition.md`.

**No stage runs without separate human approval, and agents never run
them.** Every `run` command calls the real Jev API and spends budget. The
offline commands (`pilot-check`, `fit`, `report`, `verdict`) read the local
database only.

## Setup (once per dataset)

```bash
cp configs/exp2.example.json configs/exp2.json          # synthetic, study exp2
cp configs/exp2-ecb.example.json configs/exp2-ecb.json  # ECB, study exp2-ecb
```

Fill `model` / `extra_body` / `pricing` in the local copies as for
Experiment 1. Split sizes and prompts are frozen before the pilot; never
change `split_sizes`, `seed`, `window`, `horizon` or `stride` afterwards (that
changes the dataset identity and discards the answers). The credential is
read from the environment by the SDK; `run` fails fast without it.

Below, `C` stands for one local config (`configs/exp2.json` or
`configs/exp2-ecb.json`); repeat every stage for both datasets. Commands
use bash syntax (start `bash` first from fish or another shell).

```bash
C=configs/exp2.json   # or configs/exp2-ecb.json
```

A and C must be **rerun** here: the Experiment 2 split sizes change the
dataset identity, so Experiment 1 answers cannot be reused. Their experiment
ids are `<study>-A-run1` and `<study>-C-batched`; the new arms are
`<study>-Ap`, `<study>-Ap5` and `<study>-D`. L, M, Majority and Const are
deterministic and need no calls.

CLI arm names: `Ap` is A', `Ap5` is A'x5.

Calls per sample: A 1 + C 1 + A' 1 + A'x5 5 + D 5 = 13.

## Stage 1: pilot (30 x 13 = 390 calls per dataset)

All five LLM arms on the `pilot` split:

```bash
for ARM in A C Ap Ap5 D; do venv/bin/python -m src.experiments.exp2_cli run --config $C --arm $ARM --split pilot; done
venv/bin/python -m src.experiments.exp2_cli pilot-check --config $C
```

**Gate before stage 2.** `pilot-check` prints the `PilotCheck` JSON and exits
with code 1 when a §9 stop rule fires or any of the five arms has no stored
pilot run ("missing pilot arm ..."): an arm's invalid rate above 5%, any
NaN/infinite indicator, or a Judge whose probability std across pilot inputs
is below 0.01 (reported as uninformative). On a stop, do not continue: report
the reasons. `--arms` restricts the check to a subset for diagnostics only;
the gate is the default (all five arms). The pilot may only stop the run or expose a definite defect; a
defect fix means the pilot is rerun, and prompts are never tuned for
accuracy. Also read the measured token budget before approving stage 2.

**After any pilot defect fix, use a NEW `study_id` and a NEW `db_path`** in
the local config before rerunning the pilot. The answers of the old pilot
are discarded, not reused: `run` skips every unit that already has a
recorded call, so resuming the old study would silently mix stale answers
with the fixed prompts. As a backstop, each Experiment 2 run stores a
`judge_fingerprint` (sha256 over every Judge's id, version and prompt) and
`run` refuses to resume an experiment whose fingerprint differs.

## Stage 2: D and A' on calib, thresh, test (900 x 6 = 5,400 calls per dataset)

```bash
for ARM in D Ap; do
  for S in calib thresh test; do venv/bin/python -m src.experiments.exp2_cli run --config $C --arm $ARM --split $S; done
done
```

`run` is resumable: rerunning skips every unit that already has a recorded
call (failed calls are not retried). `--max-units N` caps one invocation.

## Stage 3: A'x5, A and C on calib, thresh, test (900 x 7 = 6,300 calls per dataset)

```bash
for ARM in Ap5 A C; do
  for S in calib thresh test; do venv/bin/python -m src.experiments.exp2_cli run --config $C --arm $ARM --split $S; done
done
```

## Stage 4: test_shift for D and A' (300 x 6 = 1,800 calls per dataset)

```bash
for ARM in D Ap; do venv/bin/python -m src.experiments.exp2_cli run --config $C --arm $ARM --split test_shift; done
```

A'x5, A and C are skipped on `test_shift` (not needed there); L, M and
Majority are computed offline. `test_shift` is a secondary check, never part
of the success rule.

Total per dataset: 390 + 5,400 + 6,300 + 1,800 = 13,890 calls (about 13,900),
before ties and reruns.

## Offline: fit, then report

`fit` must precede `report`. It refuses a config describing a different
dataset and refuses to freeze while any calib/thresh unit has no recorded
call (`--allow-incomplete` overrides; freezing is irreversible). A rerun reuses
the frozen fit.

```bash
for ARM in D Ap Ap5 A C; do venv/bin/python -m src.experiments.exp2_cli fit --config $C --arm $ARM; done
for ARM in D Ap; do venv/bin/python -m src.experiments.exp2_cli fit --config $C --arm $ARM --decisions-split test_shift; done
venv/bin/python -m src.experiments.exp2_cli report --config $C --split test
venv/bin/python -m src.experiments.exp2_cli report --config $C --split test_shift
```

`report` and `verdict` refuse when any reported LLM arm has no frozen fit or
lacks a recorded call for any unit of the evaluated split (missing units
would otherwise count as invalid samples and silently shrink the
eligibility set). `--allow-incomplete` overrides this and puts an
"incomplete run" warning note into the report and the verdict output.
`report --json` prints the full report (every number behind the markdown);
the markdown already lists tokens, latency p50/p95, Platt parameters and
fallbacks, the SKIP-target analysis and the reliability bins. `verdict`
prints, per dataset, the eligibility n, each LLM arm's invalid rate and Platt
fallback, and all report notes.

After stage 2 only, a preliminary `test` report (no A'x5, no attribution,
verdict not final) is available. Fit D and A' first, then report:

```bash
venv/bin/python -m src.experiments.exp2_cli fit --config $C --arm D
venv/bin/python -m src.experiments.exp2_cli fit --config $C --arm Ap
venv/bin/python -m src.experiments.exp2_cli report --config $C --split test --arms D Ap --preliminary
```

## Verdict across datasets (§11)

Needs both datasets complete through stage 3 and fitted; ECB is primary.

```bash
venv/bin/python -m src.experiments.exp2_cli verdict --ecb-config configs/exp2-ecb.json --synthetic-config configs/exp2.json
```

Raw results stay in the git-ignored `workspace/`.
