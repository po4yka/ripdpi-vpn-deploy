---
id: SEC-1787916931540401
title: Preserve SSH access during restricted management network rollout
kind: feature
status: doing
area: security
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: sec-1787916931540401-restricted-admin-network-rollout
created: 2026-08-28
updated: 2026-08-28
related_tasks: []
---

## Goal

Preserve working OpenSSH access while removing confirmed legacy ownership overlap and adding restricted Tailnet administration, with autonomous recovery after interrupted management-network changes.

## Acceptance criteria

- Recognized packaged-main defaults and known legacy 10/20/50 fragments migrate through a dedicated four-file entrypoint with full effective SSH policy equality and no algorithm, key, port or authentication change.
- Persistent guest recovery handles interruption, timeout and reboot; fresh strict direct and Tailnet SSH proof is required before confirmation. Unknown or corrupted state is retained for explicit recovery, never silently overwritten.
- Restricted Tailnet administration preserves public emergency access, DNS, routing, unrelated ACL access and VPN traffic. Cloud firewall changes have separately tested external rollback.
- Local failure tests, pinned-distro validation and exact-source hosted CI pass. Real isolated staging rehearsal and serial fleet acceptance remain required; fixtures and source CI are not live proof.

## Implementation ownership

- Primary owns this isolated branch, planning, SSH transaction helper, operator entrypoint and integration. Delegated work is limited to the SSH planner/tests and the atomic recovery-bundle installer, its adapter, units, playbook and dedicated tests after strict planning validation. Primary owns transaction core, operator wrapper/Makefile and integration; independent review is read-only.
- The coordinator owns inventory guards, the five existing site pre-task `always` tags, and the backup configuration entrypoint. Do not edit those lanes; coordinate shared Makefile edits before publication.
- Reuse the separate single-owner SSH policy task without importing algorithm changes or unrelated branch history. That task remains responsible for algorithm pins and its own acceptance.
- The readiness correction delegates only `sshd_migrate.py`, `sshd_transaction.py` and their two existing unit-test files to the implementation worker. Primary retains planning, task state, test-count documentation and integration; the independent reviewer remains read-only. Bundle trust-root, units, controllers and other teams' files are excluded.
- The separate baseline-convergence worktree assigns only `sshd_ownership.py` and its existing test file to the planner worker. Primary owns core/adapter integration, actual parser upgrade tests, baseline/bootstrap/controller integration and shared-file coordination. PR118 remains frozen; no node actions or parallel fixed-port test runs belong to this source slice.
- The transaction worker owned the schema-two core/adapter and historical-reader tests; the planner worker owned only `sshd_ownership.py` and its existing test file. Primary retains documentation, integration and all live acceptance ownership.

## Execution boundaries

Local source implementation can proceed now. No host, provider or policy mutation belongs to the local implementation gate. Staging provisioning waits for the approved existing executor, verified account price/credit and exact-resource cleanup within 48 hours and the approved total cap. Tailnet ACL application needs a separately approved fresh diff. Production promotion requires observed staging recovery and an explicit serial maintenance window.
