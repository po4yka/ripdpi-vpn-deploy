# Change: Restore deployment and VPN rollback reliability

Task ID: `OPS-1792263187492070`

## Why

Six verified defects can bypass a planned check, mix environment state backups,
leave accepted VPN traffic blocked, or allow command work to survive cleanup.
Operators need ordered deployment and complete recovery after rejected changes.

## What Changes

- Honor blue-green dry-run intent and serialize dependent Make phases.
- Select Terraform backups by exact provider, environment and timestamp.
- Keep firewall policy coherent with accepted transport state on failure and tagged runs.
- Retain AWG binaries, shared units and configurations through consumer acceptance.
- Reclaim CI command descendants before teardown, even after their leader exits.
- Add executable regression tests and run local and hosted source gates.
- No intentional breaking operator interface, dependency upgrade or live rollout.

## Capabilities

### New Capabilities

- `operations/deployment-recovery`: ordered source-controlled deployment and recovery boundaries.

### Modified Capabilities

- None; this change repairs implementation defects without relaxing existing transport contracts.

## Impact

- Operator shell scripts, CI subprocess control, Ansible firewall and AWG publication.
- Terraform provider configuration, secret schema, protocol versions and credentials stay unchanged.
