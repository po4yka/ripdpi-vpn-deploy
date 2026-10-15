---
id: ANS-1791996027408136
title: Recover interrupted ingress deploys and bind operator verbs to one node
kind: bug
status: review
area: ansible
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1791996027408136-operator-recovery-paths
created: 2026-10-14
updated: 2026-10-15
related_tasks: []
---

## Goal

An interrupted protected ingress deploy no longer wedges the node: the next deploy compensates through the existing rescue and dry-run reports the condition without mutation. `rotate-credentials`, `rollback-xray` and `rollback-config` act on exactly one named inventory alias, and rotation stays within the selected environment. Operator runtime rollback is tested at its ownership boundary and documented truthfully. Found by the 2026-10-14 deep audit (H1, H2, H3 residual), re-verified at `82b14824`.

## Acceptance criteria

- Every requirement in `openspec/changes/ans-1791996027408136-operator-recovery-paths/specs/operations/operator-recovery-paths/spec.md` maps to a passing test recorded in the change verification.
- The three operator verbs refuse without an exact `ANSIBLE_LIMIT`, and operator docs show the per-node form.
- `make check` passes locally (environment-only failures reported as such) and required CI checks pass on the PR head.
- Gateway runtime rollback and the ingress-commit versus egress-finish window are filed as separate tasks.
