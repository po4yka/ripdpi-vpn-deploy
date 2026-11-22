---
id: TFR-1795328481774241
title: Move OpenTofu state to an encrypted Backblaze B2 backend
kind: feature
status: backlog
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

OpenTofu state and saved plans of every root are encrypted on the client and kept in a versioned, object-locked Backblaze B2 bucket with scoped keys and serialized writers, migrated exactly from the current local files.

## Acceptance criteria

- Every root has an enforced `encryption` block and a partial S3 backend; backend files hold no credentials.
- Prove backend locking across CI and the operator workstation for default and named workspaces before migration. A failed lock probe keeps local state authoritative.
- Authorized: per-root migration receipts show equal addresses and lineage, non-decreasing serial and a no-change plan.
- Restore a retained state version without GitHub using the operator state key and passphrase. Verify a competing writer cannot change that workspace during restore.
