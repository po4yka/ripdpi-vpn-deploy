---
id: SEC-1791223987683372
title: Bootstrap restricted management on existing fleet nodes
kind: feature
status: dropped
area: security
priority: critical
risk: high
owner: primary
parent: EPC-1788891270457728
blocked_by: []
spec_mode: required
openspec_change: sec-1791223987683372-bootstrap-restricted-management-on-existing-fleet-nodes
created: 2026-10-05
updated: 2026-10-08
related_tasks: []
closed_at: "2026-10-08T15:25:23Z"
closed_reason: Owner cancelled acceptance and requested removal of all acceptance resources
evidence_summary: Live acceptance is cancelled, not completed. Already merged implementation is preserved; temporary provider and local acceptance resources are being retired.
---

## Goal

Enroll existing managed fleet nodes into restricted Tailnet management from
their real named workspace, with source-bound temporary console access,
preserved VPN policy and autonomous original-policy rollback. This unblocks
the parent's serial convergence without replacing its required live gates.

## Acceptance criteria

- Canonical inventory and bootstrap requests bind the workspace, actual build
  marker, node identity, source and cleanup class before writes.
- A rendered console capability preserves shared runtime directory permissions,
  private-file isolation, existing policy and authentication, and expires.
- Reviewed managed legacy policy converts to the canonical Tailnet layout in
  the durable transaction; foreign or unexplained state refuses safely.
- Controller loss, timeout and reboot restore original policy without extending
  temporary ingress or changing SSH, resolver or routes.
- Positive real pinned public/Tailnet SSH and SFTP, protected-source local/native
  and hosted gates, guarded staging and existing-node cleanup are observed.
- A refusal-only implementation remains unfinished; this task and its parent
  never close on a fixture, partial restoration or missing acceptance category.
