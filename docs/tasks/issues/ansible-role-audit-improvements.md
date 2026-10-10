---
id: ANS-1791586652330612
title: Implement remaining Ansible role audit improvements
kind: feature
status: review
area: ansible
priority: medium
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ansible-role-audit-improvements
created: 2026-10-10
updated: 2026-10-10
related_tasks: []
status_detail: PR 282 review findings fixed; all 83 exact-source hosted checks passed with zero CodeQL findings and 22 resolved threads. Local acceptance remains blocked by one unchanged smoke fixture Ansible deadline; no archive or feature closure.
---

## Goal

Implement the remaining audit improvement contracts and add observed source
results to existing PR 282, preserving all P1/P2 fixes and unrelated work.

## Acceptance criteria

- I07-I15/F43 have runnable correction or demonstrated current correctness; I01-I06 retain their bounded evidence and explicit artifact qualifications.
- Per-device auth, bounded retention/replay protection, interrupted activation, private metrics and durable notification intent have positive and failure-path proof.
- No unsafe deletion, credential exposure, compatibility shim, guard relaxation or fake live evidence is introduced.
- Reviewed snapshots, complete local gates, independent review and exact-source hosted checks pass before handoff.
- Missing full morphology source does not fabricate capability or close its unfinished feature; source/CI is distinct from provider, live client and human acceptance.
