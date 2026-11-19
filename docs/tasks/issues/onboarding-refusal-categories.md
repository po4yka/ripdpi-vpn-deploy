---
id: OPS-1795083694897534
title: Report specific onboarding refusal categories in SSH baseline failure receipts
kind: bug
status: done
area: operations
priority: medium
risk: standard
owner: Deploy maintainer
parent: null
blocked_by: []
spec_mode: required
openspec_change: ops-1795083694897534-onboarding-refusal-categories
created: 2026-11-19
updated: 2026-11-19
related_tasks: []
closed_at: "2026-11-19T13:19:03Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: PR 643 merged as 248f21e4 and a9592f19; main CI run 44523008717 passed 84/84 jobs; local make check and narrow suites recorded in verification.md
---

## Goal

A deploy-mode onboarding refusal reports its fixed category in the private SSH baseline failure receipt instead of `onboarding-refused`, without paths, addresses, aliases or secret values. The missing-Terraform-workspace case reports `recovery-promotion-payload-input-unavailable`.

## Acceptance criteria

- The client emitter prints `client-payload: payload-input-unavailable` when `terraform-env.sh output` fails.
- The installer, finalization and baseline controller carry that category to the receipt reason `recovery-promotion-payload-input-unavailable`.
- Known `recovery-promotion-*` refusals reach the receipt as themselves; unknown failures stay generic at each layer.
- Behavioural tests run each layer and assert the reported category.
