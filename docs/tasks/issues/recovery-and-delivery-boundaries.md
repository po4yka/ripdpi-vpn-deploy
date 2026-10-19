---
id: OPS-1792305989358872
title: Repair recovery and delivery boundaries
kind: bug
status: review
area: operations
priority: high
risk: high
owner: maintainer
parent: null
blocked_by: []
spec_mode: required
openspec_change: recovery-and-delivery-boundaries
created: 2026-10-18
updated: 2026-10-19
related_tasks: []
status_detail: Record exact source, local gate, protected merge and complete main CI acceptance without deployment.
---

## Goal

Close all eight repeated-audit deployment, backup, recipient and DHCPv6
boundaries without deploying or accessing live credentials.

## Acceptance criteria

- Reserved default aliases cannot target production state through blue-green.
- Partial backup or restoration cannot replace accepted state.
- Share publication grants only owner/nginx-group read access.
- RIPDPI export refuses unsupported Hysteria port hopping before publication.
- Restore drills require all selected profile artifacts.
- A disabled mirror cannot continue scheduled publication.
- Recovery documentation includes complete current SSH/deployment prerequisites.
- Scoped DHCPv6 works while unrelated interfaces and sources remain denied.
- Regressions and required local/remote checks pass; reviewed source is merged.
- No deployment or production credential action is performed.
