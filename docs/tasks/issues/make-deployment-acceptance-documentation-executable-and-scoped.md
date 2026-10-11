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
updated: 2026-10-11
spec_reason: docs-only
related_tasks: []
status_detail: Integrated source cf01f94a640913412f3316b5cb288881639712ce passed all protected-main hosted checks in run 38134843683; recorded source scope and external qualifications are preserved. Archive-readiness verification passed; authorized lifecycle completion is in progress.
closed_at: "2026-10-11T15:05:12Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Frozen review fec70c9dc7747dc53e008379430fa7b03dd7005a has 29 successful PR checks and 15 dependency-selected not-applicable skips; no failures or pending checks. Cancelled predecessor references and canonical Python lint/parity commands corrected; all 7 instruction checks and 155 tasking/workspace/firewall tests plus 22 subtests passed. Task contracts valid; documentation-only acceptance.
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
