---
id: OPS-1795083694897534
title: Report specific onboarding refusal categories in SSH baseline failure receipts
kind: bug
status: review
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
---

## Goal

A deploy-mode onboarding refusal reports its fixed category in the private SSH baseline failure receipt instead of `onboarding-refused`, without paths, addresses, aliases or secret values. The missing-Terraform-workspace case reports `recovery-promotion-payload-input-unavailable`.

## Acceptance criteria

- The client emitter prints `client-payload: payload-input-unavailable` when `terraform-env.sh output` fails.
- The installer, finalization and baseline controller carry that category to the receipt reason `recovery-promotion-payload-input-unavailable`.
- Known `recovery-promotion-*` refusals reach the receipt as themselves; unknown failures stay generic at each layer.
- Behavioural tests run each layer and assert the reported category.
