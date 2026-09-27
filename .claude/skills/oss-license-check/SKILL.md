---
name: oss-license-check
description: Use when adding a new third-party dependency or adopting a code snippet from an open-source project.
---

# OSS License Check

## Rule

A human verifies license compatibility before a third-party dependency or copied snippet is
adopted. Do not adopt code under a copyleft license (GPL, AGPL, LGPL) by copying it verbatim.

## How

1. When proposing a new dependency, state its license (check `package.json`/`pyproject.toml`
   metadata, the project's `LICENSE` file, or its package registry page).
2. Prefer permissive licenses (MIT, Apache-2.0, BSD) for new dependencies.
3. If a copyleft-licensed library looks necessary, flag it explicitly to a human instead of
   adding it silently — do not decide license compatibility unilaterally.
4. When implementing an algorithm you recognize from a specific OSS project, write a clean-room
   implementation from the underlying idea rather than transcribing the source. If you are unsure
   whether your output is a paraphrase or a copy, say so and ask a human to compare.

## Common mistakes

- Treating "it's on GitHub" as equivalent to "it's freely reusable."
- Copying a GPL-licensed function and only renaming variables.
- Adding a new dependency without checking its license because it already appears in a search
  result's code snippet.
