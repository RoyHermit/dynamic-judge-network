---
name: context-checkpoint
description: Use before clearing context, after a long interruption, or after a meaningful implementation batch, spec, or plan gets approved — to leave a concise handoff that the next session (yours or a teammate's) can resume from.
---

# Context Checkpoint

## Rule

A session's context (chat history, reasoning) does not survive `/clear`, a long interruption, or a handoff to a teammate's own AI session. A repo-tracked checkpoint file does. Write the handoff to a file inside the repository — never to an AI tool's personal/local memory (e.g. a coding assistant's own memory store, kept outside the repository under the user's home directory) — because a teammate who clones the repository cannot see anything that isn't committed to git.

Use this at a natural work boundary (a spec or plan just got approved, a meaningful implementation batch just landed, or context is about to be cleared/interrupted) — not after every edit.

## How

1. Read the canonical spec or plan and the current unfinished section.
2. Inspect `git status --short`, the current branch, and the latest commit.
3. Update `.ai/memory/CURRENT_STATE.md` (or an equivalent path already established in the project).
4. **Commit this file to git.** If it is new, confirm it is not caught by `.gitignore` before relying on it — an untracked checkpoint file is invisible to everyone but you.
5. A local commit alone only survives `/clear` or an interruption *in this same worktree*. If the handoff is meant for a teammate or a different machine, a commit that hasn't been pushed is still invisible to them. This project reserves `git push` for a human to run — report the commit hash/branch and ask the human to push it, and do not tell them the handoff is ready for a teammate until they confirm it has been pushed.
6. Keep the file at 60 lines or fewer.
7. Link to the canonical spec or plan; do not copy its body.
8. Record only confirmed decisions, current blockers, the next executable step, and fresh verification results.
9. Do not include raw chat, command output, secrets, or speculative history.
10. Tell the user the checkpoint is ready before they clear the context (same-worktree resumption only needs the commit from step 4; a teammate/cross-machine handoff also needs step 5's push).
11. When the goal is complete, restore the file to an inactive state instead of retaining it as a session archive.

## Common mistakes

- Saving the handoff to an AI tool's personal/global memory instead of this file — that storage is local to one person's machine, invisible to a teammate who clones the repository, and defeats the point of the checkpoint.
- Declaring a teammate/cross-machine handoff ready right after committing, without pushing (or confirming the human pushed) — a commit that only exists in the local worktree is exactly as invisible to a teammate as an AI tool's personal memory would be.
- Letting the checkpoint file get caught by `.gitignore` — verify it is actually tracked before treating it as the source of truth.
- Copying the full spec/plan body into the checkpoint instead of linking to it — the checkpoint then drifts out of sync with the canonical document.
- Updating the checkpoint after every small edit — reserve it for real boundaries, or it becomes noise nobody reads.
- Leaving stale "current state" in the file after the goal is done — restore it to an inactive/empty state so the next checkpoint isn't read against outdated context.
