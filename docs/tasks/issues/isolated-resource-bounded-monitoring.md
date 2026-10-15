---
id: MON-1792080593038468
title: Deliver isolated resource-bounded monitoring acceptance
kind: feature
status: done
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
closed_at: "2026-10-15T17:33:32Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Exact source f6ad803e97237d8d8ec3839284d84db974ea986c passed all 88 CI jobs in 38768887914: actual bounded collector replay and outage, historical delivery after native agent rollback, and isolated real Kuma timing, persistence and encrypted restore. No external infrastructure or human receipt claimed. Local focused checks passed; monolithic check limitation is preserved in committed acceptance."
---

## Goal

Deliver the implemented private collector, bounded vmagent sender and independently deployable Uptime Kuma observer with positive isolated runtime acceptance. This is the source-only successor to MON-1790835036464962 after the owner excluded external infrastructure on 2026-10-15. No live deployment or human notification receipt is claimed.

## Acceptance criteria

- Actual isolated sender/collector processes preserve exact historical samples across restart, enforce configured resource boundaries, authenticate private ingestion and recover rejected activation without changing public nginx.
- The canonical enabled collector scenario passes the bounded ten-node cardinality workload: 42,000 current/historical/churn samples with exact values and timestamps under unchanged ceilings.
- Pinned Kuma accepts qualified pushes, detects missing signals, preserves monitor state and restores encrypted backups in isolation; relay states remain honest about failed or absent external delivery.
- Full source checks, snapshots, independent security review and exact-source selected hosted CI pass. Every stated native test must run without selected skips.
- Provider access, real-host rollout, real Telegram delivery, human receipts, live client performance and cutover are excluded. Deployment safeguards remain mandatory for any future rollout; this task does not accept it.

## Source acceptance scope (2026-10-15)

Per the owner-approved criteria revision, source acceptance requires focused Mac
regressions, snapshots, full-history/staged gitleaks and complete unchanged
exact-SHA hosted source/native checks. The local monolithic attempt failed on a
registry timeout; its retry was cancelled after 32 minutes still queued. No full
local success is claimed; global and deployment gates remain unchanged.
