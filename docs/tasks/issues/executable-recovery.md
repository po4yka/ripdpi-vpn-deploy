---
id: OPS-1792678016174902
title: Implement executable Path A recovery with crash resume
kind: feature
status: doing
area: operations
priority: high
risk: high
owner: maintainer
parent: null
blocked_by: []
spec_mode: required
openspec_change: executable-recovery
created: 2026-10-22
updated: 2026-10-22
related_tasks: []
---

## Goal

Execute the supported UpCloud Path A recovery from reviewed Git and SOPS,
resume by observed postconditions after failure, and retain device continuity
through a surviving dedicated publisher.

## Acceptance criteria

- Exact manifest, source, account, resource and saved-plan admission precedes mutation.
- Real provisioning, management admission, full deployment and final device acceptance execute.
- Lost responses and process interruption resume without duplicate creation or invented proof.
- Dedicated publisher topology and UpCloud support are explicit; destroyed publisher recovery remains excluded.
- Positive workflow and failure regressions, local gate, independent review, PR and main CI pass.
- No live deployment is performed or claimed during source delivery.
