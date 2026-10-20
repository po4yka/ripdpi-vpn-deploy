# Change: Repair recovery and delivery boundaries

Task ID: `OPS-1792305989358872`

## Why

The repeated deployment audit found eight remaining boundary failures. Distinct
environment names can select the same production state, interrupted state backup
and restore can publish partial files, recipient publication can expose private
files or unsupported transport settings, and disabled mirror units can remain
active. Restore verification and the recovery procedure omit required inputs.
The guest firewall can also block DHCPv6 address acquisition after restart.

## What Changes

- Refuse the reserved environment name `default` before provisioning or private input access.
- Publish encrypted state and restored state only after successful completion.
- Restrict published share bundles to their owner and nginx group.
- Refuse unsupported RIPDPI Hysteria port hopping before publication.
- Verify all required backup artifacts for the effective profile.
- Stop mirror publication when its toggle becomes false while retaining replay authority.
- Document the complete SSH recovery and deployment prerequisite sequence.
- Admit only scoped DHCPv6 address-acquisition traffic through the guest firewall.
- No live deployment, credential rotation, provider mutation or client implementation change is included.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `operations/deployment-recovery`: enforce environment isolation, complete recovery inputs, protected recipient publication and restart-safe network prerequisites.

## Impact

- Operator scripts, Ansible backup/firewall/subscription-host roles, recipient generation, recovery runbooks and regression tests.
- Existing `prod` state mapping, supported official sing-box port hopping and per-device authority remain intact.
- The invalid `default` environment alias is refused. This does not move existing production state.
- No new production dependency or secret schema field is required.
