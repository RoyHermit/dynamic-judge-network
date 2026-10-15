# Hook Strategy

This template wires one `PreToolUse` guard to Claude Code and Codex.

The guard reads `tool_input.command` and exits with status 2 only for broad
recursive delete commands targeting `/`, the home directory, the current
directory, or a wildcard representing the current directory.

## Boundaries

- This is a best-effort guardrail, not a security boundary.
- Claude Code and Codex require project trust before project hooks run.
- Scoped cleanup such as `rm -rf build/cache` remains allowed.
- Git workflow, AWS deployment checks, memory reminders, session context, and
  completion verification are intentionally not hooks.
- CI and project verification commands remain the enforcement mechanism for
  correctness.
