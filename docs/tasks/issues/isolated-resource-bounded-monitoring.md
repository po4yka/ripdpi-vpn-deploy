---
id: MON-1792080593038468
title: Deliver isolated resource-bounded monitoring acceptance
kind: feature
status: doing
area: monitoring
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: mon-1792080593038468-isolated-resource-bounded-monitoring
created: 2026-10-15
updated: 2026-10-15
related_tasks: [MON-1790835036464962]
---

## Goal

Deliver the implemented private collector, bounded vmagent sender and independently deployable Uptime Kuma observer with positive isolated runtime acceptance. This is the source-only successor to MON-1790835036464962 after the owner excluded external infrastructure on 2026-10-15. No live deployment or human notification receipt is claimed.

## Acceptance criteria

- Actual isolated sender/collector processes preserve exact historical samples across restart, enforce configured resource boundaries, authenticate private ingestion and recover rejected activation without changing public nginx.
- The canonical enabled collector scenario passes the bounded ten-node cardinality workload: 42,000 current/historical/churn samples with exact values and timestamps under unchanged ceilings.
- Pinned Kuma accepts qualified pushes, detects missing signals, preserves monitor state and restores encrypted backups in isolation; relay states remain honest about failed or absent external delivery.
- Full source checks, snapshots, independent security review and exact-source selected hosted CI pass. Every stated native test must run without selected skips.
- Provider access, real-host rollout, real Telegram delivery, human receipts, live client performance and cutover are excluded. Deployment safeguards remain mandatory for any future rollout; this task does not accept it.
