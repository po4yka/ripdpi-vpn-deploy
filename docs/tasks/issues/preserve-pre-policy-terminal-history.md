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
spec_mode: not-required
openspec_change: null
created: 2026-09-09
updated: 2026-09-09
spec_reason: regression-tested-single-module
related_tasks: []
status_detail: Historical policy versioning and regression pass; real High purge proof and hosted checks remain pending.
---

## Goal

Keep task history purgeable when a terminal transition was valid under the
project contract committed at that revision, while retaining the committed
review requirement for every transition made after policy activation.

## Acceptance criteria

- The project config explicitly versions committed-review enforcement, with
  historical configs that predate the field interpreted as policy version 0.
- Prospective and committed deletion validation read the policy from the exact
  terminal transition revision rather than applying the current config
  retroactively.
- A regression proves a pre-policy `doing` to `done` transition remains
  purgeable after activation, while existing current-policy negative tests
  continue to reject the same transition.
- The real High terminal record can be purged through `taskctl`, and the full
  task contract suite passes.
