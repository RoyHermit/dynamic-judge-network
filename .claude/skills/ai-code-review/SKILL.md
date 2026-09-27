---
name: ai-code-review
description: Use when reviewing AI-generated code — your own before declaring an implementation task done, or a teammate's/AI's before merge.
---

# AI Code Review

## Rule

AI-generated code passes syntax and often passes tests while still carrying
design-level defects a human wouldn't write and standard linters can't catch:
inline duplication instead of local abstraction, monolithic files instead of
separated responsibilities, and code that runs but reads like the wrong
language. Treat this failure mode as expected, not occasional — review these
four dimensions explicitly instead of relying on general code review to
surface them incidentally:

1. **Decomposition by purpose.** Does each file/function correspond to one
   coherent intent, or is it a "modular mirage" — split into multiple files
   for appearance, with the same responsibility scattered across them or
   unrelated responsibilities crammed into one? File-count separation is not
   the same as logical separation.
2. **Abstraction level.** Neither under- nor over-abstracted. Under:
   repeated inline logic that should be one function/type ("Abstraction
   Smell" — the AI's default is copy-paste, not extraction). Over: a
   generic/pluggable layer built for a variation that doesn't exist yet.
3. **Separation of concerns.** No single function/class/file doing
   input handling, business logic, and I/O/persistence all at once
   ("Modularisation Smell" / God Class — the AI's default without an
   explicit constraint is a monolithic script).
4. **Idiom match to the language in use.** Code should read like the target
   language, not like another language translated into it (e.g. manual
   getter/setter pairs in Python, callback-style code in a language with
   native async, exceptions used as control flow where the language
   convention is return values, or vice versa).

A fifth dimension worth checking alongside these four, because it's a
common failure point for generated code:

5. **Security, by concrete threat class, not vibes.** Check for specific,
   well-known risk classes — injection, broken authorization/access control,
   authentication/session handling, input validation, secrets/credential
   handling, and vulnerable/unverified dependencies — rather than reading
   for "does this look risky." Generated code can introduce any of these
   flaws as readily as hand-written code, so check for them explicitly
   instead of assuming safety because the code otherwise looks reasonable.
   (If the project has adopted a specific standard, e.g. a named OWASP Top
   10 edition, check against its actual published category list rather than
   an approximate one.)

These five are review criteria — properties of the code itself. Separately,
*how* a reviewer engages with AI output matters as much as what they look
for: accepting AI output without structured verification is the biggest
amplifier of the risks above — skimming code because it "looks like it
should work" is how the defects above make it past review unnoticed. That
makes a sixth thing mandatory, but as a reporting requirement, not a review
question:

6. **State what was actually verified.** A one-line note of what the
   reviewer (human or AI) actually ran/checked — not just "looks correct."

## How

1. Before declaring an implementation task done, or before opening/approving
   a PR containing AI-generated code, walk the five review dimensions above
   against the diff — don't fold this into a generic "does it work" pass.
2. Pay closer attention on OOP-heavy changes: encapsulation, generics,
   polymorphism, and inheritance are the specific areas where AI-generated
   code is weakest.
3. Run automated static analysis/linters first (whatever the project's
   verification config specifies) to clear mechanical issues, so the human
   review time goes to the five dimensions above — a linter won't catch
   "modular mirage" or a wrong-language idiom.
4. If a dependency was newly introduced by the generated code, confirm it
   actually exists and is the intended package (AI-generated code
   occasionally references a plausible-sounding, non-existent package).
5. If review is delegated — to a teammate, a separate AI review pass, or any
   project-specific review skill/subagent — hand over the five dimensions
   above as an explicit checklist instead of an open-ended "review this
   code"; a reviewer given a specific rubric finds more than one given an
   open-ended prompt. Dimension 6 is not something to delegate; it's a report
   the primary implementer owes regardless of what the delegated review
   finds.
6. Record dimension 6 (what was verified: commands/checks run, skipped
   checks, residual risk) in the task's completion note or PR description,
   separately from the pass/fail review outcome.

## Common mistakes

- Treating "tests pass" or "no linter errors" as sufficient — none of the
  five review dimensions above are mechanically enforced by tests or
  standard linters.
- Reviewing file-by-file without asking whether the *split itself* makes
  sense (dimension 1) — a diff can look clean per-file and still be a
  modular mirage across files.
- Accepting AI-generated code with only a skim because it "looks like it
  should work" — this is exactly how the defects above make it past review
  unnoticed.
- Applying this checklist only to review, never to the generation prompt —
  if the same smell (e.g. monolithic file) recurs, constrain it explicitly
  in the prompt/spec next time rather than catching it in review every time.
