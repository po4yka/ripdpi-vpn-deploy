---
id: OPS-1795327950629406
title: Create the private ops repository and map the operator kit onto it
kind: feature
status: backlog
area: operations
priority: high
risk: high
owner: Planner
parent: EPC-1795327697650892
blocked_by: []
spec_mode: required
openspec_change: ops-1795327950629406-private-ops-repository-w1
created: 2026-11-22
updated: 2026-11-22
related_tasks: []
---

## Goal

A private ops repository holds inventories, tfvars, toggles, the catalog and receipts, pins the public repository by full SHA, and every operator kit item has one recorded authority (ops repository, B2 recovery prefix, GitHub environment, password manager or temporary).

## Acceptance criteria

- `scripts/validate-ops-repo.py` rejects a non-SHA pin, plaintext secrets, private keys, state and plan files, and catalog entries without an authority, with unit tests.
- `docs/how-to/local-operator-kit.md` contains the kit mapping table.
- Authorized: the private repository exists, passes the validator and gitleaks, and the inventory comparison receipt shows equality with the MacBook kit.
