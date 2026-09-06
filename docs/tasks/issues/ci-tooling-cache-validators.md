---
id: TST-1788681428475698
title: Cache CI tooling and consolidate Python validators
kind: chore
status: done
area: testing
priority: medium
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-09-06
updated: 2026-09-06
spec_reason: tooling-only
related_tasks: []
status_detail: Implementation and local checks complete; hosted cold/warm cache evidence and required-context migration remain before closure.
closed_at: "2026-09-06T08:18:43Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "c4598713f1b4d0f401107500a7edb5527fafaf09: full hosted CI run 34020979760 passed; attempt 2 reran observability_agent with exact pip and Galaxy cache hits and passed. Setup decreased from 32s to 16s; seven Python validator commands passed in one 29s job versus 93s summed prior jobs. 44 local tests, actionlint, zizmor and pre-commit passed. Live required contexts migrated from five legacy names to python validators; all other protection fields and strict mode verified unchanged."
---

## Goal

Reduce repeated Python/Galaxy dependency installation and runner setup for
short validators while preserving the complete required CI coverage.

## Acceptance criteria

- All main-CI Python consumers share hash-verified installs with pip caching.
- Galaxy caches use the Ansible lock, collection pins and platform identity;
  installation and version reconciliation still run after restoration.
- Five Python validator jobs become one with every original command retained.
- Failure, cancellation or skipped validation cannot pass required checks.
- Cold and warm hosted runs pass, with observed pip/Galaxy cache hits on the warm run.
- The required contexts and documentation match the new job before main delivery.
