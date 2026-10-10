---
id: ANS-1791562764586678
title: Repair P2 Ansible role lifecycle and configuration audit defects
kind: bug
status: review
area: ansible
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ansible-role-p2-remediation
created: 2026-10-09
updated: 2026-10-10
related_tasks: []
status_detail: All 32 confirmed P2 paths covered in existing PR282; both independent reviews approve; local full gate and all82 exact-source hosted checks pass. Source-only scope; no rollout or archival.
---

## Goal

Repair or demonstrate current correction of all 32 confirmed P2 role audit paths,
investigate the six P2 candidates, and add validated source to existing PR 282.

## Acceptance criteria

- Every confirmed P2 ID has a source repair or demonstrated current correction; investigation candidates retain explicit evidence and qualification.
- Positive runtime/parser/delivery behavior, check mode, failure compensation and enabled-to-disabled/idempotent transitions are exercised; refusal-only output does not close a capability.
- Existing P1 boundaries, unrelated work, retained authority/queues and private inputs remain intact.
- Intended snapshots, required local checks, independent review and exact-source hosted checks pass.
- Source PR evidence remains separate from real deployment, external client and human acceptance; no live actions are claimed.
