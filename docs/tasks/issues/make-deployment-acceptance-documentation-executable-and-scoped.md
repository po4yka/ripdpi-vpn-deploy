---
id: DOC-1791476695959389
title: Make deployment acceptance documentation executable and scoped
kind: chore
status: review
area: docs
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-08
updated: 2026-10-08
spec_reason: docs-only
related_tasks: []
---

## Goal

Make the deployment and acceptance instructions usable from the current operator
interfaces, with bounded authorization and evidence required for the selected scope.

## Acceptance criteria

- Document fresh/recreated nodes, ordinary redeployment and incident recovery separately.
- Correct unsupported mandatory drills, misleading cleanup/lifetime guarantees and stale examples against current code.
- Preserve implemented authentication, host-key, per-device credential, promotion and exact-resource cleanup checks.
- Clarify sensitive Terraform artifacts, source parity, selected CI checks and reuse of existing authorization.
- Independent documentation and safety reviews, relevant local contract checks and exact-head PR checks pass.
- Documentation and instruction updates only; infrastructure and runtime behavior remain outside this task.
