---
id: XRY-1792776853872491
title: Separate reviewed Xray pins from upstream release status
kind: bug
status: doing
area: xray-config
priority: high
risk: standard
owner: transport-resilience
parent: null
blocked_by: []
spec_mode: required
openspec_change: xray-reviewed-pin-status
created: 2026-10-23
updated: 2026-10-23
related_tasks: ["po4yka/RIPDPI#TRN-1792776009699531"]
---

## Goal

Keep local pin parity independent of upstream release availability.

## Acceptance criteria

- Exactly one repository pin must match the example; missing, duplicate and mismatched declarations fail.
- The current security release and compiler fix are recorded without promoting private pins or removing staging.
- Focused regressions, full source checks, and exact-head hosted checks pass.
