# Knowledge Index

Entry point for research and design work. Read the authority order, then open
sections by number — do not read whole documents by default (they are
800–1300 lines).

## Authority order

When documents conflict, the higher row wins.

| # | Document | Role |
|---|----------|------|
| 1 | `docs/context/djn-research-direction-update.md` | Direction update; controls conflicts |
| 2 | `docs/context/djn-research-input-spikingbrain.md` | Supplementary input; hypotheses only |
| 3 | `docs/context/djn-research-input-decision-model-abstraction.md` | Supplementary input; non-binding |
| 4 | `docs/context/dynamic-judge-network-context.md` | Original context; superseded where 1 differs |

Implemented foundation (code-level truth, not research):
`docs/superpowers/specs/2026-09-27-project-foundation-design.md` and
`docs/superpowers/plans/2026-09-27-project-foundation.md`. Code and tests
outrank all research text on what exists today.

## Section index

Section numbers are the `## N.` headings; open them with `grep -n '^## '`.

### Direction update (1)
- §2 Novelty boundary · §3 Research lineage
- §7–8 Deterministic before Judge; gates as network nodes
- §9–11 Activation Waves; wave vs provider request; fetched/activated/used
- §12–14 Evidence State, its ablation, "missing is not neutral"
- §15–17 Relative vs absolute gate; `SKIP`; counter-evidence
- §18 Cost-aware sparse execution · §19 Refined baselines A–F

### SpikingBrain input (2)
- §3–5 Event-driven activation; adaptive threshold hypothesis
- §8 Judge group selection · §9–10 Evidence State
- §12–13 Judge Sparsity metric; accuracy–sparsity frontier
- §16–18 Waves integration; initial implementation stays deterministic
- §19–20 Threshold ablation; research questions RQ-S*

### Decision-model abstraction input (3)
- §3 Separations to preserve · §4 Raw output and provenance
- §5 Provider-specific calibration · §6 Batching vs sparsity
- §7 Architecture effect vs provider effect
- §8–10 Candidate questions, metrics, sequence · §11 Novelty boundary

### Original context (4)
- §3 Central hypothesis · §4 Basic architecture · §5 Versus ensembles
- §6 Judge diversity · §7 Biological ideas (7.1–7.7)
- §9–11 Initial PoC: High & Low, Judge candidates, outputs
- §12 Baselines A–E

## Maintenance

- Adding a research doc: add a row to the authority order and its key
  sections here, and link it from `README.md`.
- This index lists only sections confirmed against the headings; extend it
  rather than guessing. Open items live in `.ai/memory/TASKS.md`, state in
  `.ai/memory/CURRENT_STATE.md`.
