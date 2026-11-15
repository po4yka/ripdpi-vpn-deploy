# Change: Keep revoked devices revoked and bind secret delivery to pinned hosts

Task ID: `SEC-1794728936979277`

## Why

The 2026-11-15 audit found paths on which a revoked credential stays usable, and paths on which device credentials go to a host whose identity is not pinned:
- The `config` action of the transport rollback republishes the previous Xray configuration and does not call the revocation guard that the other rollback paths call. A device UUID that was removed can return.
- A share bundle is a static file tree. After a token is revoked, the subscription route answers 410, but the share route still serves the device configuration. Converge never removes a bundle directory that left the declared list.
- `scripts/issue_sub_token.py` sends the device payload, which includes the AmneziaWG private key, through `ssh` with no host-key, agent or configuration options.
- The subscription mirror trusts the build worker's host key on first use, and its SSH key and backup password belong to the same user as the internet-facing service.
- `scripts/rotate-secrets.sh` changes the recipients of the SOPS file but keeps the data key, so a removed recipient can decrypt later versions.

`SEC-1794287701595900` owns pinning the host key before first contact with a new node. This change uses that pinned file and does not replace it.

## What Changes

- The `config` rollback refuses a previous configuration that would re-admit a revoked or removed client identity.
- Revoking a token removes its share bundle, and a revoked token cannot get a new one. Bundles that are not revoked are kept, as before.
- Every SSH call that carries a device payload ignores the user's SSH configuration, requires a pinned host key and forwards no agent.
- BREAKING: a mirror with a remote source requires a pinned `known_hosts` entry from secrets, and `mirror.ssh_opts` no longer accepts host-key options. The pull runs as its own user, which owns the mirror key and the backup password; the publisher copies the fetched tree.
- BREAKING: `rotate-secrets.sh` rotates the SOPS data key after it updates the recipients.

## Capabilities

### New Capabilities

- `security/revocation-and-pinned-delivery`: revocation holds across rollback and share bundles, device payloads go only to pinned hosts, and recipient removal rotates the data key.

### Modified Capabilities

- None.

## Impact

- Ansible: `ansible/roles/runtime-release/files/transport_runtime_rollback.py`, `ansible/roles/subscription-host/`.
- Scripts: `scripts/issue_sub_token.py`, `scripts/rotate-secrets.sh`, the device revocation path that updates the subscription host.
- Secrets: a new required mirror host-key value when the mirror is enabled.
- Docs: `docs/how-to/multi-operator.md`, `docs/reference/secrets.md`, the subscription host guide.
- Operations: a subscription host with the mirror enabled needs the new secret before its next deploy.
