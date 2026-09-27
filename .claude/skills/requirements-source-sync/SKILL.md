---
name: requirements-source-sync
description: Use when a stakeholder answer or confirmation updates a structured source of truth (a hearing-answer spreadsheet/CSV, a tracked decision log) that a requirements or design document also summarizes in prose — before editing that prose directly from the raw answer, and before considering the update complete.
---

# Requirements Source Sync

## Overview

When a structured source of truth changes (a hearing-answer CSV, a confirmed decision log, etc.) and a prose document also summarizes that same data, update the structured source first and derive the prose update from it — never edit the prose independently from the raw incoming answer. Documents that summarize the same source from two angles (a progress-tracking view and a detail view) commonly drift apart silently: the tracking view gets updated because someone is actively working through open items, while the detail view — which restates the same data in full — gets forgotten.

## When to use

- A stakeholder/customer answer arrives that changes a value already recorded in a structured source (hearing CSV, spreadsheet export, tracked decision log)
- Confirming or updating any status field in a structured source that a requirements/design document chapter summarizes
- Not for: fixing wording or typos in the prose that don't reflect any change in the underlying source

## Rules

1. **Update the structured source first.** Record the new value/status there, not directly in the prose.
2. **Then update every prose section that summarizes that source** — not just the one you were already looking at. Search for every place the same topic is restated; a "progress tracking" view (e.g., an open-items list) and a "detail" view (e.g., the full requirements section) commonly summarize the same underlying row independently, and updating one does not update the other.
3. **Run the project's mechanical sync check, if it has one, before considering the update complete.** Only mark the source as "synced" after confirming the prose actually reflects the change — never run an "update"/"mark synced" step before making the corresponding prose edit.
4. **If there's no mechanical check yet and the drift risk is real** (a source that changes repeatedly, multiple prose sections summarizing it), build one. Exact content-equality between a structured row and its prose summary usually isn't checkable — prose paraphrases by design. A hash-based staleness detector ("this source row changed since its summary was last confirmed") is far cheaper to build and catches the same failure mode: it can't tell you the prose is *correct*, but it reliably tells you when it needs re-checking, which is what silently failed before.

If you build a hash-based staleness detector, make it fail-closed: a missing/unreadable manifest must fail the check rather than silently re-initialize (an auto-initializing check can never detect drift after its own state file is lost or not checked out), and writing/confirming "synced" state should require an explicit, deliberate action, not a side effect of the read-only check. Key rows by content that's actually unique (or detect and reject duplicates/blanks explicitly) rather than by position, and build any composite key/hash from an unambiguous serialization (e.g., a JSON array of the fields) rather than delimiter-joined strings, which collide when a field happens to contain the delimiter.
