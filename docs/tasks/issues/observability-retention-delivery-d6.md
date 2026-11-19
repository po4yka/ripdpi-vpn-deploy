---
id: MON-1795086847564764
title: Enforce observability retention and prove Telegram alert delivery
kind: feature
status: backlog
area: monitoring
priority: medium
risk: high
owner: Planner
parent: EPC-1795085241910080
blocked_by: []
spec_mode: required
openspec_change: mon-1795086847564764-observability-retention-delivery-d6
created: 2026-11-19
updated: 2026-11-19
related_tasks: []
---

## Goal

Retention is documented and enforced for Prometheus, the vmagent queue, logs and field reports, and Telegram alert delivery is proven by a receipt.

## Acceptance criteria

- One reference table lists the retention of every observability data class and each value is enforced by rendered configuration.
- A test or check fails when a retention value is missing or unbounded.
- A real Telegram delivery receipt for a test alert is recorded after explicit operator authorization.
- Field-report data has no raw retention; only aggregates live in Prometheus under its retention.
