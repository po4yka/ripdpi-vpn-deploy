---
id: TFR-1795328481774241
title: Move OpenTofu state to an encrypted, locked object storage backend
kind: feature
status: done
area: terraform
priority: high
risk: high
owner: Planner
parent: EPC-1795327697650892
blocked_by: [TFR-1795328347526492]
spec_mode: required
openspec_change: tfr-1795328481774241-encrypted-remote-state-w3
created: 2026-11-22
updated: 2026-11-24
related_tasks: []
status_detail: All execution steps are done. The owner removed the extended lock probe storage run and the full W2 production acceptance as closure requirements on 2026-11-24
closed_at: "2026-11-24T14:57:09Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: All six execution steps are done. Protected-main ci run 45410025050 passed at f9d6a5139. Live receipts w3-scw-lock-probe-20261122, w3-migration-20261122 (four workspaces, equal addresses, no resource changes) and w3-restore-drill-20261122 record the original lock probe, migration and restore drill. The extended lock probe storage run and the full W2 production acceptance were not performed; the owner removed them as closure requirements on 2026-11-24.
---

## Goal

Every root encrypts state and saved plans. Fleet provider roots keep state in the versioned, object-locked Scaleway bucket. Migrate each workspace with scoped keys and serialized writers.

## Acceptance criteria

- Every root enforces encryption. Fleet provider roots use a partial S3 backend. The inert exception root and the disposable CI checkout use isolated encrypted local state. Backend files hold no credentials.
- Prove backend locking across CI and the operator workstation for default and named workspaces before migration. A failed lock probe keeps local state authoritative.
- Authorized: per-root migration receipts show equal addresses and lineage, non-decreasing serial and a no-change plan.
- Restore a retained state version without GitHub using the operator state key and passphrase. Verify a competing writer cannot change that workspace during restore.
