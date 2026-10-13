---
id: MON-1791825755591250
title: Repair Telegram delivery and service monitoring audit defects
kind: bug
status: done
area: monitoring
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: observability-alerting-audit-fixes
created: 2026-10-12
updated: 2026-10-13
related_tasks: []
status_detail: Full pinned local gate, exact-source hosted checks and independent review passed at 8846bf2c0cee51e36f42eca3b49255e67f81ed09; deployment and real notifications remain excluded.
closed_at: "2026-10-13T18:12:06Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Source 8846bf2c passed the complete local gate and hosted required checks; e9e8517e committed the reviewed acceptance snapshot. Canonical archival completed successfully.
---

## Goal

Repair the observed alert delivery and monitoring defects and prepare one source-only PR, preserving private authority and the existing rollout hold.

## Acceptance criteria

- All audited source defects have real behavior fixes and meaningful failure/recovery regressions.
- Producer/consumer, PromQL, snapshots, affected role scenarios and required repository checks are run and their observed results recorded.
- Independent review covers the complete source diff and security boundaries.
- Exact-source PR checks are recorded; task stays in review until required hosted acceptance passes.
- No deployment or real Telegram message; live and human acceptance remain separate.
