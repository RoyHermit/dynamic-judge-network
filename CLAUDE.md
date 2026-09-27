# Project Development Rules & AI Guardrails

Durable rules only. Task-specific procedures live in `.claude/skills/`, not here —
each rule below names its skill inline where one applies. Skills with no standing
Core rule are discovered by their own trigger description instead.

## Security & Data Protection
- Never output, request, or work with real API keys, passwords, private keys, or
  `.env` contents. Use placeholders (`MOCK_API_KEY`, `example.com`).
- Deploy/mutate/delete against production, customer staging, or a real database
  is human-only — never automate it. Read-only diagnostics against those
  environments are allowed only under the `cloud-readonly-diagnostics` skill's
  conditions.
- Never run `git push`, force-push, or bulk file deletion automatically. A human
  executes these.
- Replace real customer names and system-specific identifiers with placeholders
  (e.g. "Customer A", "System X") in requirements and design discussions.
- Assume by default that the customer can browse or clone this repository's
  Git (direct-delivery is the common case, not a special one). Never commit
  internal-only business documents — cost estimates, margin/buffer strategy
  notes, negotiation reasoning. Keep them outside Git or in a `.gitignore`d
  path; removing them later requires a destructive history rewrite on a repo
  the customer may have already cloned.

## Testing
- Generate test data and mocks from schemas/type definitions. Never use real
  production data, database dumps, or real logs. See the `mock-test-data` skill.

## Code & Licensing
- Never copy verbatim from copyleft-licensed OSS (e.g. GPL). Use standard
  algorithms and clean-room implementations.
- A human verifies license compatibility (MIT/Apache-2.0 etc.) before adopting a
  third-party dependency. See the `oss-license-check` skill.

## Code Review
- Before declaring an implementation task done, review AI-generated code (your
  own or a teammate's/AI's) against decomposition, abstraction level,
  separation of concerns, language idiom, and concrete security threat
  classes — passing tests is not sufficient. See the `ai-code-review` skill.

## Context Continuity
- Before clearing context, after a long interruption, or after a spec/plan
  gets approved, write a handoff into a repo-tracked file — never into an AI
  tool's personal/local memory, which is invisible to teammates who clone
  the repository. See the `context-checkpoint` skill.

## Web Search
- Web search is limited to general technical research (official docs, library
  specs, error debugging). Never combine it with client-specific names or
  keywords.

## Recurring Review Findings
- If the same review finding (human or AI) repeats 2-3 times, stop re-reviewing
  it manually — promote it into `dangerous-commands.txt`, `block-patterns.txt`,
  or a new skill so it is caught mechanically next time.

## Known Limits (read before assuming full coverage)
- The hooks in this repo are an auxiliary guardrail, not a substitute for
  sandboxing, human approval, or backups. They can be disabled locally by
  anyone with repo write access.
- "No real data in tests" and "no client-specific web search" cannot be
  mechanically enforced by the hooks — regex cannot reliably distinguish real
  customer data from realistic mock data. Follow these rules by discipline, not
  because a hook will catch a violation.
- The `PostToolUse` audit hook detects secret-like patterns that appear only in
  command *output* (not input), but it cannot guarantee retroactive removal
  from the conversation. Treat it as a detection/log layer, not a guarantee.
- `.claudeignore` in this template is a token-saving convenience, not a
  security boundary — it is not an official Claude Code feature and does not
  reliably stop a file from being read. File-path protection for secrets is
  handled entirely by `pre-tool-enforce.sh`'s `block-patterns.txt` scan.
- On native Windows without Git Bash installed, the hook scripts (`bash "..."`)
  cannot run at all, so the hook-based guardrails (dangerous-command detection,
  secret-pattern detection) are unenforced there. Only the native
  `permissions.deny` rules (`Bash(...)`/`PowerShell(...)`) still apply. Git
  Bash is a required prerequisite for the hook layer to work on Windows.
- `permissions.deny` entries are literal command-prefix matches, not regex —
  they cannot express "these flags anywhere in the command" the way the hook's
  regex patterns can. On native Windows without Git Bash (where this is the
  *only* active layer, per the point above), a common invocation such as
  `Remove-Item C:\work -Recurse -Force` (path before the flags) is **not**
  blocked, because it does not start with the literal deny prefix
  `Remove-Item -Recurse -Force`. Treat the native-only configuration as a
  partial backstop, not equivalent coverage to the hook layer (Codex review
  finding, unresolved).

## Tech Stack
- Runtime: Python 3.11+
- Package manager: pip (venv)
<!-- TBD: lint/test commands. Fill in once decided. -->
