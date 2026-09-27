---
name: meeting-minutes-reference
description: Use when you need to check whether a past customer decision or confirmation already exists, or when reviewing new customer meeting minutes against existing requirements/decisions — before asking the user to recall from memory, and when minutes reveal a changed decision.
---

# Meeting Minutes Reference

## Rule

A project that persists customer meeting minutes (e.g. in a `meeting-minutes/`
folder, one file per review) has a written record that is more reliable than a
person's live recall of what was said, by whom, and when. Two rules follow
from that:

1. **Check the archive before asking.** Before asking the user "was this
   already confirmed with the customer?" or "when was this decided?", search
   the persisted meeting-minutes archive first. Only ask the user when the
   archive has no record or the record is ambiguous. Relying on recall when a
   written record exists wastes the person's time and risks misattribution
   (a decision recalled as the customer's can turn out to have been the
   vendor's own idea, or vice versa) or wrong dates.
2. **A changed decision is a signal to size, not just to fix.** When new
   minutes contradict an earlier recorded decision, don't silently correct the
   requirements doc and move on. Report the contradiction explicitly, then
   assess how much rework or scope the change touches. A minor wording change
   just gets corrected; a change that invalidates work already designed or
   built is worth flagging as potential grounds for a schedule or scope
   renegotiation with the customer — that assessment itself is a deliverable
   the person may want to use in that conversation.

## How

1. Persist customer meeting minutes as they happen, one file per review, in a
   dedicated folder separate from other requirements sources (hearing sheets,
   the requirements draft itself). Anonymize customer and individual names
   per the project's identification policy before committing, if one exists.
2. Before asking the user to confirm a past decision's existence, date, or
   attribution, search the minutes archive. Cite what you find with its
   source file and date instead of asking.
3. When new minutes are provided, cross-reference their decisions against
   both the requirements document's current claims and earlier minutes files.
4. On a match: no action needed beyond noting confirmation if useful.
5. On a contradiction: report it to the user before changing anything.
   Ask or assess together how much prior work (design decisions, code,
   estimates) depended on the old version. Small blast radius → apply the
   correction. Large blast radius → flag it as renegotiation material in
   addition to applying the correction.

## Common mistakes

- Asking the user to recall a decision from memory when the archive already
  has a dated, attributed record of it.
- Treating AI-generated minutes as infallible — they are a stronger source
  than memory, not a perfect one; verify ambiguous points instead of taking
  every line at face value.
- Silently correcting a contradicted decision without surfacing that it
  contradicts a prior one, or without assessing whether the change is costly
  enough to be worth raising with the customer.
- Storing meeting minutes wholesale in the same location as structured
  hearing/requirements sources — keep them in their own folder so the
  requirements sources stay easy to scan.
