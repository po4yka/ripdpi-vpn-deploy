---
id: CIC-1788902865968549
title: Preserve pre-policy terminal history validation
kind: bug
status: review
area: ci
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: cic-1788902865968549-preserve-pre-policy-terminal-history
created: 2026-09-09
updated: 2026-09-09
related_tasks: []
status_detail: Monotonic activation, required OpenSpec, full regressions, and real High purge validation pass; exact-head hosted checks and review remain pending.
---

## Goal

Keep task history purgeable when a terminal transition was valid under the
project contract committed at that revision, while retaining the committed
review requirement for every transition made after policy activation.

## Acceptance criteria

- The project config explicitly versions committed-review enforcement, with
  historical configs that predate the field interpreted as policy version 0.
- Prospective and committed deletion validation derive monotonic activation
  from the exact terminal transition's first-parent config ancestry rather
  than applying the current config retroactively.
- A regression proves a pre-policy `doing` to `done` transition remains
  purgeable after activation, while existing current-policy negative tests
  continue to reject the same transition.
- A downgrade regression proves version 0 or an omitted field cannot disable
  version 1 after activation.
- The real High terminal record can be purged through `taskctl`, and the full
  task contract suite passes.
