---
id: MON-1790835036464962
title: Deliver resource-bounded monitoring without dedicated VPS nodes
kind: feature
status: doing
area: monitoring
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: resource-bounded-observability
created: 2026-10-01
updated: 2026-10-01
related_tasks: []
---

## Goal

Deliver bounded metrics and actionable alerts using existing VPN capacity, with no dedicated monitoring VPS and Uptime Kuma on an independent existing observer host. This replaces the deployment intent of `docs/tasks/issues/staging-observability-telegram-acceptance.md` without claiming its outstanding acceptance checks passed.

For the active contract, historical task boundaries and acceptance ownership,
see the [current contract and task history](../../OBSERVABILITY-OPERATIONS.md#current-contract-and-task-history).

## Acceptance criteria

- Co-hosted collector and agents run under enforced aggregate limits and pass measured VPN non-regression and storage-exhaustion tests on an approved existing host.
- Existing primary Telegram delivery, independent node/pipeline loss alarms, recovery, credential rotation, and private authenticated ingestion work in observed live drills.
- No new recurring paid resource is created; existing observer capacity, private ingress, distinct notification authority and encrypted backup/restore are verified before activation.
- All changed contracts and callers migrate together; local gates and applicable hosted CI pass, with live and client-path evidence reported separately.
- The task remains open until the positive runtime capability and required human alert receipts are verified. Refusal-only, planning-only, fixture-only, and missing-access states cannot close it.
