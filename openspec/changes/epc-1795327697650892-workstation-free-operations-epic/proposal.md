# Change: Operate the VPN service without the operator workstation

Task ID: `EPC-1795327697650892`

## Why

Terraform state and the whole operator kit (catalog, receipts, inventories, tfvars, SOPS documents) exist only on the operator MacBook. When the MacBook is off, nobody can deploy, recreate a burned node, rotate a credential or issue a device. The operator wants a Claude cloud session, the repository CI and one dedicated egress VPS to do all of this. A Claude cloud session reaches the network only through an HTTP proxy, and its environment variables are readable inside its VM, so it must hold no credentials.

## What Changes

- Add a coordinated program of seven child changes, W1 to W7, in dependency order:
  - W1 private ops repository and kit mapping.
  - W2 Terraform to OpenTofu toolchain migration.
  - W3 encrypted OpenTofu state on Backblaze B2.
  - W4 revocable CI identities in scoped GitHub environments.
  - W5 secretless egress proxy node for provider APIs.
  - W6 Porkbun DNS root.
  - W7 ops repository workflows and the Claude cloud environment.
- BREAKING (after W7): the MacBook stops being the only authority for state and operator configuration. It becomes a break-glass client of the same remote state, the same ops repository and the same encrypted documents.

## Capabilities

### New Capabilities

- `operations/workstation-free-operations`: ordering, secret-placement and acceptance rules for the program.

### Modified Capabilities

- None directly; each child change names its own.

## Impact

- All layers: Terraform/OpenTofu roots, Ansible (new egress role), SOPS recipients, GitHub settings of a new private repository, Tailnet policy, provider accounts.
- No live action is part of this planning change. Each child names the live steps that need separate operator authorization.
