---
id: DOC-1791476695959389
title: Make deployment acceptance documentation executable and scoped
kind: chore
status: done
area: docs
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-08
updated: 2026-10-12
spec_reason: docs-only
related_tasks: []
status_detail: Accepted integrated runtime source cf01f94a640913412f3316b5cb288881639712ce passed all 86 protected-main jobs in run 38134843683. Recorded verification results and external scope qualifications are preserved.
closed_at: "2026-10-11T21:51:07Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Integrated runtime source cf01f94a640913412f3316b5cb288881639712ce passed all 86 protected-main jobs in run 38134843683. Recorded requirement-specific verification and external qualifications are preserved. Complete local gate components passed: 6,340 portable tests, 22 subtests, 297 CLI tests, 206 baseline transfers and 57 shell tests. Every assertion and deadline is retained; production code is unchanged."
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
