# Change: Provide restricted Tailnet administration with recoverable network rollout

Task ID: `SEC-1787916931540401`

## Why

Public-IP allowlists have repeatedly stranded management access. The last fleet assessment did not establish a working, restricted Tailnet management path. The SSH ownership change validates new layouts but cannot migrate the live legacy 10/20/50 fragments, and current network changes have no autonomous rollback after controller disconnection.

## What Changes

- Add opt-in ordinary OpenSSH over Tailnet, restricted to approved management devices, while retaining direct emergency SSH and provider-console recovery.
- Enroll nodes without changing host identities, SSH authentication, DNS, routes, forwarding, or existing VPN listeners.
- Introduce explicit ownership-only migration with identical effective SSH settings before separately validated hardening changes.
- Apply network changes one host at a time with durable local rollback and fresh independent SSH verification; cloud firewall rollback uses an external controller.
- BREAKING: overlapping managed SSH directives and unrecognized migration layouts become hard failures. There is no fallback that silently weakens authentication or removes unknown files.

## Capabilities

### New Capabilities

- `security/restricted-admin-network`: Restricted Tailnet OpenSSH and recoverable management-network changes.

### Modified Capabilities

- None. The existing SSH ownership change defines the policy contract; this change supplies the explicit migration and rollout mechanism without claiming that the existing change has completed live acceptance.

## Impact

- Ansible baseline, firewall and a dedicated management role/playbook; controller inventory and rollout entrypoint; cloud-init ownership cleanup for newly provisioned nodes.
- Tailnet access policy and node registration; pinned Tailscale package dependency with secrets never stored in source or output.
- Existing SSH ownership and UpCloud activation changes remain separately tracked. No new public management listener, transport replacement, or automatic credential rotation.
