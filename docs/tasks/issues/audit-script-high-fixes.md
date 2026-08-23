---
id: SCR-1787420815046709
title: Fix high-priority audit findings in operator scripts
kind: bug
status: done
area: scripts
priority: high
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-22
updated: 2026-08-23
spec_reason: tooling-only
related_tasks: []
closed_at: "2026-08-23T04:56:20Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "All 54 required CI checks green on PR #84 final SHA 9aa0e5e, merged to main as 4e26e7e; focused tests (burn-check metrics, destroy CI mode, audit-log hooks, liveness sentinel installer) and full pytest tests/unit green; shellcheck -S warning and bats input-validation clean; make validate green"
---

## Goal

Describe the observable outcome.

## Acceptance criteria

Define verifiable completion criteria.
