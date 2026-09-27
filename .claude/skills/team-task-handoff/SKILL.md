---
name: team-task-handoff
description: Use when splitting new development work across multiple people who each run their own AI coding session — before decomposing a spec, writing a plan that will be divided, or assigning implementation tasks to teammates.
---

# Team Task Handoff

## Rule

Splitting work across people without a written contract between the pieces is what causes
integration rework (mismatched API shapes, diverging domain models discovered only at merge
time). Before assigning work to more than one person, produce a written plan that satisfies all
four:

1. **Independent decomposition, decided upfront, with a build order.** Split the spec into units
   that can each be built and tested standalone. Identify which unit(s) others depend on (shared
   data model, API contract) — those go first, alone, and land on the trunk branch before
   dependent units start.
2. **Interface contract per unit, frozen before work starts.** Each unit's spec states exactly
   what it *consumes* from other units (function/API signatures, types) and what it *produces*
   for others to consume. A unit's assignee should be able to work from their unit plus this
   contract, without reading every other unit's implementation.
3. **Task sized to fit one person's single AI-session budget.** An oversized unit gets split
   further along an existing interface boundary — never at an arbitrary midpoint that cuts through
   an undecided contract.
4. **Interface changes are broadcast, not silent.** If an assignee needs to change what their unit
   produces mid-implementation, they notify every consumer and update the written contract before
   merging. Silent interface drift is the direct cause of integration failures this skill exists
   to prevent.

**Only split when each resulting unit clears requirement 1's bar** (independently buildable and
testable on its own). A single small task doesn't clear that bar — keep it as one task. Splitting
it adds coordination cost with no offsetting benefit.

**When the shared foundation in requirement 1 is a data model, draft it as a lightweight ER
diagram before any unit starts.** Schema drift is the costliest kind of interface drift to fix
late — once units have written code against diverging assumptions, unwinding it means touching
every unit instead of one diagram. An ER diagram is also cheap to hand to a fresh AI session as
grounding context, which prevents each session from re-deriving (and subtly reinventing) the
schema on its own. It doesn't need to be the final, polished schema for formal design docs —
a rough working version that every assignee and every session can point to is enough; refine it
into the formal deliverable later.

## How

1. Decompose the spec into independent units; decide build order. Foundational units (shared
   schema, API contract, core domain model) go first, alone, and merge to the trunk branch before
   any dependent unit starts.
2. For each unit, write: its file/component scope, what it *consumes* from other units (exact
   signatures/types), what it *produces* for others.
3. Check each unit's estimated size against the assignee's session budget. If it doesn't fit,
   split further — always along an existing interface boundary, never mid-interface.
4. Assign one unit per person. Each works in an isolated workspace (e.g. a separate git worktree)
   so parallel work doesn't collide on files.
5. Mid-implementation change to a unit's *produces* side: assignee notifies affected consumers and
   updates the written contract before merging — not after.
6. Review integration against the written contract, not just against the diff — a PR that changes
   a *produces* signature gets checked against what dependent units assumed it would be.

## Common mistakes

- Splitting by technical layer (frontend/backend) or by feature, without first freezing the
  interfaces those pieces share — this is the exact pattern that causes integration rework.
- Assigning a unit before its *consumes* dependencies are decided — the assignee guesses, and the
  guess diverges from what gets built.
- Splitting a task just because multiple people are available, even though the pieces don't clear
  the "independently testable" bar — coordination overhead ends up exceeding the benefit.
- Changing a shared interface mid-task without telling the other assignees — discovered only at
  merge, when it's most expensive to fix.
