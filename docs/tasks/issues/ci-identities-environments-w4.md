---
id: SEC-1795328680299474
title: Issue revocable CI identities in scoped GitHub environments
kind: feature
status: backlog
area: security
priority: high
risk: high
owner: Planner
parent: EPC-1795327697650892
blocked_by: []
spec_mode: required
openspec_change: sec-1795328680299474-ci-identities-environments-w4
created: 2026-11-22
updated: 2026-11-22
related_tasks: []
---

## Goal

CI has its own age, SSH, Tailnet and provider identities, each only in the GitHub environments that need it, with every mutation running only after the operator merges, and each identity can be revoked alone.

## Acceptance criteria

- `scripts/validate-ops-environments.py` enforces the environment matrix, the merge gate and the untrusted-input rule, with unit tests. Cover a combined address and host-pin change and revoke a CI recipient against a retained fixture data key.
- `admin_ssh_public_keys` and the exclusive `baseline` authorized_keys pass Molecule add and revoke.
- Authorized: environments, CI identities, re-encrypted SOPS files, Tailnet tags and grants, and least-privilege provider tokens exist and are catalogued.
