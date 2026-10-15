---
id: SEC-1791735853691219
title: Repair project audit security and lifecycle defects
kind: bug
status: done
area: security
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: project-audit-repairs
created: 2026-10-11
updated: 2026-10-16
related_tasks: []
status_detail: Integrated main source 3010dfb517b84cd7fbe9c3512b30b87d63b64fe8 passed all 88 source/native CI jobs in 38792726270 and both CodeQL analyses; focused local evidence and the unsuccessful monolithic local attempt are recorded. No external rollout or real notification receipt claimed.
closed_at: "2026-10-15T20:36:38Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Integrated main source 3010dfb517b84cd7fbe9c3512b30b87d63b64fe8 passed all 88 CI jobs in 38792726270 and both CodeQL analyses with zero open alerts. Actual native integration 138+2 XHTTP+1 AWG and four real recovery cases passed; enabled collector/agent and pinned Kuma isolated runtimes passed. Approved focused Mac and complete unchanged hosted source gate verified; local monolithic timeout and queued cancellation remain recorded. No external deployment or real notification receipt.
---

## Goal

Repair the sixteen audit cases with exact identity, resource scope and complete publication, then prepare one reviewed PR.

## Acceptance criteria

- Every REQ-AUDIT requirement has a behavioral regression and an in-scope implementation.
- Focused tests, reviewed snapshots, make check and independent review have recorded outcomes.
- The PR contains only owned repair changes; exact-source CI is recorded separately.
- No live deployment or credential operation is part of source acceptance.

## Source acceptance scope (2026-10-15)

Per the owner-approved criteria revision, source acceptance requires focused Mac
regressions, snapshots, full-history/staged gitleaks and complete unchanged
exact-SHA hosted source/native checks. The local monolithic attempt failed on a
registry timeout; its retry was cancelled after 32 minutes still queued. No full
local success is claimed; global and deployment gates remain unchanged.
