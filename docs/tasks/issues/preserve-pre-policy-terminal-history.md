---
id: CIC-1788902865968549
title: Preserve pre-policy terminal history validation
kind: bug
status: doing
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
status_detail: Trusted-base implementation and 103-test taskctl suite pass; exact-source full gate and hosted review remain required.
---

## Goal

Keep task history purgeable when a terminal transition was valid under the
project contract committed at that revision, while retaining the committed
review requirement for every transition made after policy activation.

## Acceptance criteria

- The project config explicitly versions committed-review enforcement while
  preserving the distinction between an omitted field and explicit version 0.
- Prospective and committed deletion validation derive monotonic activation
  from the exact terminal transition's first-parent config ancestry and an
  activation boundary already present in the trusted validation base rather
  than applying a contributor-controlled later config retroactively.
- A regression proves a pre-policy `doing` to `done` transition remains
  purgeable after activation, while existing current-policy negative tests
  continue to reject the same transition.
- A downgrade regression proves version 0 or an omitted field cannot disable
  version 1 after activation.
- An unversioned peer remains fail-closed, and pre-policy compatibility accepts
  only the historical `doing` to `done` form rather than arbitrary sources.
- Base-aware validation rejects a policy-only downgrade even when no task is
  deleted in the validation range.
- A stale lane forked before activation cannot merge a direct `doing` to `done`
  transition committed after activation as legacy history.
- A change based on an unversioned trusted base cannot forge `doing` to `done`,
  activate the policy later in the same change, and thereby make the earlier
  transition valid in base-aware or federation validation.
- The real High terminal record can be purged through `taskctl`, and the full
  task contract suite passes.
