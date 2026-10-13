---
id: MON-1791825755591250
title: Repair Telegram delivery and service monitoring audit defects
kind: bug
status: doing
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
status_detail: Fixture and bounded I/O follow-up passed focused checks and review; renewed full local gate and exact-head CI are pending.
---

## Goal

Repair the observed alert delivery and monitoring defects and prepare one source-only PR, preserving private authority and the existing rollout hold.

## Acceptance criteria

- All audited source defects have real behavior fixes and meaningful failure/recovery regressions.
- Producer/consumer, PromQL, snapshots, affected role scenarios and required repository checks are run and their observed results recorded.
- Independent review covers the complete source diff and security boundaries.
- Exact-source PR checks are recorded; task stays in review until required hosted acceptance passes.
- No deployment or real Telegram message; live and human acceptance remain separate.
