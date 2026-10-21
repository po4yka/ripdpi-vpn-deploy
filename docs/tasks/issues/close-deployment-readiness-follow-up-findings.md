---
id: OPS-1792512787218003
title: Close deployment readiness follow-up findings
kind: bug
status: done
area: operations
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ops-1792512787218003-close-deployment-readiness-follow-up-findings
created: 2026-10-20
updated: 2026-10-21
related_tasks: [ANS-1792499727513191]
closed_at: "2026-10-21T08:29:21Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Accepted protected main 86d76430707a0e6febedaf4c7c8c19351b224d36 has the same tree as PR #347 head c1c5828b. PR CI 39543684353 and 39549714130 and main CI 39557145005 passed all 92 jobs, including Molecule, native lanes and the liveness parser check. Each finding has a regression that fails on its parent. No deployment."
---

## Goal

Operator deploy paths stop for review before a Terraform apply or a site
convergence, select the intended source and target environment, and clean
decrypted secrets on every exit. Host builds, provider images and nginx logs
keep the documented toolchain, operating system and bearer-URL boundaries.

## Acceptance criteria

- Each finding has a regression that fails on the parent commit.
- Focused tests, snapshots, Terraform tests, task validation and `make check` pass.
- An independent review of the exact patch reports no unresolved defect.
