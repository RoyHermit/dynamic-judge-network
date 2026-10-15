---
name: context-checkpoint
description: Save a concise handoff after an approved spec, approved plan, meaningful implementation batch, or before clear or a long interruption.
---

# Context Checkpoint

Use this at a natural work boundary, not after every edit.

1. Read the canonical spec or plan and the current unfinished section.
2. Inspect `git status --short`, the current branch, and the latest commit.
3. Update `.ai/memory/CURRENT_STATE.md` (current state, blockers, and the next executable step).
4. Commit the file to git; confirm `.gitignore` does not catch it. Never store the handoff in an AI tool's personal/local memory — it is invisible to anyone who clones the repository.
5. Keep `CURRENT_STATE.md` at 60 lines or fewer.
6. Link to the canonical spec or plan; do not copy its body.
7. Record only confirmed decisions, current blockers, the next executable step, and fresh verification results.
8. Do not include raw chat, command output, secrets, or speculative history.
9. Tell the user that the checkpoint is ready before they clear the context. `git push` is human-only: for a teammate or cross-machine handoff, report the commit hash/branch and do not call it ready until the human confirms the push.

When the goal is complete, restore the file to an inactive state instead of retaining a session archive.
