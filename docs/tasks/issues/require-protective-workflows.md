---
id: CIC-1788634353343245
title: Require protective workflows before merge
kind: bug
status: review
area: ci
priority: high
risk: standard
owner: Codex
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-09-05
updated: 2026-09-06
spec_reason: tooling-only
related_tasks: []
status_detail: Protective workflow aggregation delivered to protected main dad8f989.
---

## Goal

Connect existing policy, image security, client-contract and pinned-binary
workflow outcomes to the branch-required CI aggregate so their failures block
merge. This is a CI wiring repair, not a change to runtime or security policy.

## Acceptance criteria

- Call all four protective workflows from required CI without path-filter gaps.
- Preserve strict success-only aggregation for failures, cancellations and skips.
- Avoid duplicate standalone PR runs, retain manual and external-drift triggers,
  and scope SARIF upload permissions to the image-scan call.
- Exercise the actual aggregate shell against success and each unsuccessful
  protective result, and observe required hosted CI before protected-main merge.
- Preserve the dirty original checkout and serialize main integration with PR159.
