---
id: ANS-1792073622616697
title: Close runtime helper files and clear CodeQL findings
kind: bug
status: review
area: ansible
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-15
updated: 2026-10-15
spec_reason: mechanical-refactor
related_tasks: []
status_detail: "Integrated main source 3010dfb517b84cd7fbe9c3512b30b87d63b64fe8 passed all 88 source/native CI jobs in 38792726270 and both CodeQL analyses; focused local evidence and the unsuccessful monolithic local attempt are recorded. No external rollout or real notification receipt claimed."
---

## Goal

Review all 59 open CodeQL alerts from the 2026-10-15 snapshot, make directory
descriptor ownership explicit, and repair remaining quality findings without
changing runtime publication, readiness or compensation contracts.

## Acceptance criteria

- Account for all 59 alerts, including findings already repaired on main.
- Retain trusted directory descriptors until transaction exit and close them on
  successful, exceptional, interrupted and failed-entry paths.
- Preserve native validator and process cleanup behavior while resolving the
  remaining import, unused-variable, mixed-return and empty-except findings.
- Pass focused Mac regressions, full-history/staged secret scanning and complete
  unchanged exact-SHA hosted source/native checks; verify CodeQL for that source.

## Source acceptance scope (2026-10-15)

The owner-approved source-only criteria require focused Mac regressions,
full-history/staged secret scanning and the complete unchanged exact-SHA hosted
source/native checks. The local monolithic attempt failed on a registry timeout;
its retry was cancelled while still queued behind the machine-wide build gate.
No full local success is claimed. Global and future deployment gates remain
unchanged.
