---
id: MON-1794937115554282
title: Silence external coverage alert during transport deploys
kind: feature
status: done
area: monitoring
priority: medium
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: required
openspec_change: mon-1794937115554282-deploy-coverage-silence
created: 2026-11-17
updated: 2026-11-19
related_tasks: []
status_detail: Live acceptance on node-c at 42a5ab8b recorded in verification.md (PR 639)
closed_at: "2026-11-19T04:56:12Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Deploy coverage silence live on node-c at 42a5ab8b: gateway audit shows main create, tail create, main delete and tail expiry; the coverage alert fired only inside the silence; main CI and dry-run passed (PR 639)."
---

## Goal

Describe the observable outcome.

## Acceptance criteria

Define verifiable completion criteria.
