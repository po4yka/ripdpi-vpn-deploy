---
id: TFR-1795328481774241
title: Move OpenTofu state to an encrypted, locked object storage backend
kind: feature
status: doing
area: terraform
priority: high
risk: high
owner: Planner
parent: EPC-1795327697650892
blocked_by: [TFR-1795328347526492]
spec_mode: required
openspec_change: tfr-1795328481774241-encrypted-remote-state-w3
created: 2026-11-22
updated: 2026-11-22
related_tasks: []
---

## Goal

Every root encrypts state and saved plans. Fleet provider roots keep state in the versioned, object-locked Scaleway bucket. Migrate each workspace with scoped keys and serialized writers.

## Acceptance criteria

- Every root enforces encryption. Fleet provider roots use a partial S3 backend. The inert exception root and the disposable CI checkout use isolated encrypted local state. Backend files hold no credentials.
- Prove backend locking across CI and the operator workstation for default and named workspaces before migration. A failed lock probe keeps local state authoritative.
- Authorized: per-root migration receipts show equal addresses and lineage, non-decreasing serial and a no-change plan.
- Restore a retained state version without GitHub using the operator state key and passphrase. Verify a competing writer cannot change that workspace during restore.
