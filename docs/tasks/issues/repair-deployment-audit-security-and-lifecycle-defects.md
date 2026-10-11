---
id: SEC-1791471757439452
title: Repair deployment audit security and lifecycle defects
kind: bug
status: review
area: security
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: deployment-audit-remediation
created: 2026-10-08
updated: 2026-10-12
related_tasks: []
status_detail: "Accepted integrated runtime source cf01f94a640913412f3316b5cb288881639712ce passed all 86 protected-main jobs in run 38134843683. Recorded verification results and external scope qualifications are preserved."
---

## Goal

Repair the 21 audited deployment security and lifecycle defects, retaining current upstream corrections, and deliver a reviewed source PR.

## Acceptance criteria

All audited items map to working behavior or verified existing fixes; regression, local and hosted source checks pass; unrelated work is preserved; no infrastructure rollout is implied. Refusal-only paths do not satisfy positive deployment behavior. Keep the task open until required evidence passes.
