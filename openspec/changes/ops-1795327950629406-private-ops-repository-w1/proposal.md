# Change: Create the private ops repository and map the operator kit onto it

Task ID: `OPS-1795327950629406`

## Why

The operator kit (`secrets/local/`, `docs/how-to/local-operator-kit.md`) exists only on the MacBook. CI and a Claude cloud session cannot read it, so nothing can run while the MacBook is off. Inventories, tfvars, toggles, the catalog and receipts are not secret, but they identify nodes and accounts, so they cannot go into the public `po4yka/ripdpi-vpn-deploy` repository or its logs. Part of W1 of epic `EPC-1795327697650892`.

## What Changes

- Define a private GitHub ops repository that holds non-secret but sensitive operator configuration: inventories, tfvars, profile toggles, `fleet.mk`, SSH config and `known_hosts`, the SOPS recipient policy, SOPS-encrypted deployment documents, the catalog, plans and receipts.
- The ops repository pins the public repository by a full commit SHA in `upstream.lock` and runs the public Make targets from that checkout.
- Define where every kit item goes: the ops repository, a B2 recovery prefix (W3), a GitHub environment secret (W4), the operator's password manager, or nowhere (temporary only).
- Add an ops repository template and a validator to the public repository that rejects plaintext secrets, unencrypted SOPS documents, state or plan files, and a non-SHA pin.
- BREAKING: the kit contract changes from "one physical kit on the MacBook" to "ops repository plus B2 recovery prefix"; the MacBook keeps a clone and the break-glass identities.

## Capabilities

### New Capabilities

- `operations/private-ops-repository`: layout, pin, content rules and kit mapping of the private ops repository.

### Modified Capabilities

- None in `openspec/specs`; the kit contract lives in `docs/how-to/local-operator-kit.md`, which this change rewrites.

## Impact

- Public repository: `docs/how-to/local-operator-kit.md`, new `docs/reference/ops-repository.md`, new `templates/ops-repo/`, new `scripts/validate-ops-repo.py` with `tests/unit/test_validate_ops_repo.py`.
- New private GitHub repository (live step, needs authorization).
- No Terraform, Ansible or secrets schema change.
