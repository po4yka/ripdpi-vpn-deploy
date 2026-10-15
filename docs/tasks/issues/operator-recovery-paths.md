---
id: ANS-1791996027408136
title: Recover interrupted ingress deploys and bind operator verbs to one node
kind: bug
status: done
area: ansible
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1791996027408136-operator-recovery-paths
created: 2026-10-14
updated: 2026-10-16
related_tasks: []
status_detail: Integrated main source 3010dfb517b84cd7fbe9c3512b30b87d63b64fe8 passed all 88 source/native CI jobs in 38792726270 and both CodeQL analyses; focused local evidence and the unsuccessful monolithic local attempt are recorded. No external rollout or real notification receipt claimed.
closed_at: "2026-10-15T20:36:36Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Integrated main source 3010dfb517b84cd7fbe9c3512b30b87d63b64fe8 passed all 88 CI jobs in 38792726270 and both CodeQL analyses with zero open alerts. Actual native integration 138+2 XHTTP+1 AWG and four real recovery cases passed; enabled collector/agent and pinned Kuma isolated runtimes passed. Approved focused Mac and complete unchanged hosted source gate verified; local monolithic timeout and queued cancellation remain recorded. No external deployment or real notification receipt.
---

## Goal

An interrupted protected ingress deploy no longer wedges the node: the next deploy compensates through the existing rescue and dry-run reports the condition without mutation. `rotate-credentials`, `rollback-xray` and `rollback-config` act on exactly one named inventory alias, and rotation stays within the selected environment. Operator runtime rollback is tested at its ownership boundary and documented truthfully. Found by the 2026-10-14 deep audit (H1, H2, H3 residual), re-verified at `82b14824`.

## Acceptance criteria

- Every requirement in `openspec/changes/ans-1791996027408136-operator-recovery-paths/specs/operations/operator-recovery-paths/spec.md` maps to a passing test recorded in the change verification.
- The three operator verbs refuse without an exact `ANSIBLE_LIMIT`, and operator docs show the per-node form.
- `make check` passes locally (environment-only failures reported as such) and required CI checks pass on the PR head.
- Gateway runtime rollback and the ingress-commit versus egress-finish window are filed as separate tasks.

## Source acceptance scope (2026-10-15)

Per the owner-approved criteria revision, source acceptance requires focused Mac
regressions, snapshots, full-history/staged gitleaks and complete unchanged
exact-SHA hosted source/native checks. The local monolithic attempt failed on a
registry timeout; its retry was cancelled after 32 minutes still queued. No full
local success is claimed; global and deployment gates remain unchanged.
