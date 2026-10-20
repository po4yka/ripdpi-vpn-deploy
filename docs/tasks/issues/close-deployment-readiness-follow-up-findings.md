---
id: OPS-1792512787218003
title: Close deployment readiness follow-up findings
kind: bug
status: doing
area: operations
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ops-1792512787218003-close-deployment-readiness-follow-up-findings
created: 2026-10-20
updated: 2026-10-20
related_tasks: [ANS-1792499727513191]
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
