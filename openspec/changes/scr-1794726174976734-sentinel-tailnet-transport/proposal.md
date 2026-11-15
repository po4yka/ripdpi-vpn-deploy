# Change: Reach the cloud liveness sentinel over its Tailnet address

Task ID: `SCR-1794726174976734`

## Why

An existing-node deploy proves the target through an external liveness sentinel on another managed node. The promotion scope check in `scripts/cloud_promotion_scope.py` reaches that sentinel only at the public IPv4 recorded in its Terraform state. The operator workstation's public address rotates often, so the provider firewall stops admitting it, and every production deploy then refuses before it changes anything. The fleet already has a pinned Tailnet management path to every node, but the sentinel check cannot use it.

## What Changes

- The sentinel's management SSH may use its Tailnet address (`100.64.0.0/10` or `fd7a:115c:a1e0::/48`) with the sentinel's inventory alias as the host key alias.
- A Tailnet route is accepted only when the key pinned for that alias equals the key pinned for the state-derived public address, so the reached host stays bound to the managed server in Terraform state.
- Any other transport that is not the state-derived public address is refused.
- The public route keeps its current behavior. Probes still run from the sentinel's public address, so the vantage stays external.

## Capabilities

### New Capabilities

- `operations/cloud-sentinel-transport`: admission of the management route to a cloud liveness sentinel.

### Modified Capabilities

- None.

## Impact

- Scripts: `scripts/cloud_promotion_scope.py` and its unit tests.
- Operator configuration: a liveness record may now set the sentinel's Tailnet address and inventory alias; the pin file must list that alias with the public address on one key.
- Documentation: `docs/how-to/deploy.md`, `scripts/DESIGN-NOTES.md`.
- Terraform, Ansible, secrets, vpnd and the protocol-liveness contract do not change.
