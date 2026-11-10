# Change: Pin the SSH host key before first contact with a new node

Task ID: `SEC-1794287701595900`

## Why

`scripts/bootstrap_readiness.py` makes the first SSH connection to a new node with `StrictHostKeyChecking=accept-new`. The operator has no earlier knowledge of the host key, so an attacker on the path between the operator and the provider can answer that connection, pass the readiness check and become the pinned host. The next deployment then sends decrypted VPN secrets to the attacker. The threat model of this repository assumes an active adversary on that path. The disposable CI lane already solves this on UpCloud: it builds a private seed disk that carries the host key, attaches it at creation and pins the public key before the first connection. Production bootstrap does not use that path.

## What Changes

- Production bootstrap on UpCloud can attach a private seed disk that supplies the SSH host key, as the disposable CI lane does today.
- Bootstrap readiness connects with strict host key checking against the seeded pin. The `accept-new` option leaves that path.
- BREAKING: a provider without a proven seed path refuses first contact unless the operator passes an explicit unpinned-first-contact acknowledgement. The run records that acknowledgement.
- Each further provider gets the seed path only after a disposable staging run proves that a private disk can be attached at creation and removed exactly.

## Capabilities

### New Capabilities

- `security/first-contact-host-key`: the trust decision for the first SSH connection to a new node, the seed that supplies the host key, and the refusal and acknowledgement rules.

### Modified Capabilities

- None

## Impact

- Terraform: the UpCloud root accepts the seed input outside `ci-staging-*`; other provider roots gain it one at a time. Seed storage becomes part of the exact resource set that destroy and the staging cleanup guards authorize.
- cloud-init: `terraform/shared/bootstrap-ssh-seed.py` runs for production nodes as well as CI nodes. `user_data` still carries only the filesystem UUID and the public key digest.
- Scripts: `scripts/bootstrap_readiness.py`, the seed builder now named `scripts/ci-ssh-seed.py`, `scripts/destroy.sh` and the cleanup guards.
- Operator: one more private artifact per node (the seed image) in the local operator kit until the node is created, and one more paid storage resource per node on providers that bill it.
