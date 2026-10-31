---
id: CIC-1792911952227614
title: Apply layered repository rules and release protection
kind: feature
status: done
area: ci
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: repository-rulesets
created: 2026-10-25
updated: 2026-10-31
related_tasks: []
status_detail: Source and live repository policy verified. PR 396 opened; final hosted CI is pending. No infrastructure deployment or merge.
closed_at: "2026-10-31T16:21:38Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Layered rulesets, release immutability, dependency coverage and PR-title validation merged as bdde127d (PR 396); live apply and readback on 2026-10-25; main run 40174238688 on the merged commit green.
---

## Goal

Apply the seven approved repository improvements while keeping the owner PR-only CI bypass.

## Acceptance criteria

- The classic-protection workflow is replaced by a policy plan/apply command with verified readback.
- Branch integrity has no bypass; only the owner can bypass CI through a PR.
- Only the CI aggregate and two GitHub Actions CodeQL contexts are branch requirements.
- Release tag updates and deletion are blocked, and future releases are immutable.
- Dependabot covers every active supported manifest with grouped weekly updates.
- Squash-only merges use validated PR titles and remove merged head branches.
- Targeted tests and the required local gate have observed results; live policy has no remaining drift.
- A PR contains only this task's changes; no infrastructure deployment or PR merge is claimed.
