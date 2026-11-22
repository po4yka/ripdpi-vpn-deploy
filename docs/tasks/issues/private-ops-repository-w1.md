---
id: OPS-1795327950629406
title: Create the private ops repository and map the operator kit onto it
kind: feature
status: dropped
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
closed_at: "2026-11-22T12:38:47Z"
closed_reason: "Lifecycle cannot close: the evidence transfer committed in baa16596 omits REQ-OPSREPO-MERGE-GATE and taskctl validates every historical transfer. The implementation (PR 683) and the live ops repository work (PR 686) are merged; a replacement task carries the capability spec and the open dry-run evidence."
evidence_summary: Implementation merged in PR 683 (aa46b097, 79 CI checks); private ops repository, owner-only merge gate and import recorded in PR 686
---

## Goal

A private ops repository holds inventories, tfvars, toggles, the catalog and receipts, pins the public repository by full SHA, and every operator kit item has one recorded authority (ops repository, B2 recovery prefix, GitHub environment, password manager or temporary).

## Acceptance criteria

- `scripts/validate-ops-repo.py` rejects a non-SHA pin, plaintext secrets, private keys, state and plan files, and catalog entries without an authority, with unit tests.
- `docs/how-to/local-operator-kit.md` contains the kit mapping table.
- Prove rejection and approval on secret-free jobs in the intended private repository before importing inputs. Compare `plan`, `inventory` and dry-run selection from separate checkouts with the kit, and pass the validator and gitleaks.
