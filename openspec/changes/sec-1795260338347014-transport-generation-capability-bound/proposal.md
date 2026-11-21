# Change: Bound the capabilities of the transport generation controller

Task ID: `SEC-1795260338347014`

## Why

The fleet audit of 2026-11-20 found that `ripdpi-transport-generation.service` runs as root with the full capability bounding set. The unit has a hardening floor (`NoNewPrivileges`, `ProtectSystem=strict`, namespace and address family limits) but no `CapabilityBoundingSet`, so a defect in the controller can use any root capability. The controller starts and stops units, drops to frontend UIDs, restores nftables state after a reboot and refreshes the WARP namespace. Change `ans-1795163654691828-udp-node-audit-hardening` declined to set the bound, because a wrong set stops every Xray and Hysteria frontend and the acceptance tests are Linux-native lanes.

## What Changes

- The unit gains a `CapabilityBoundingSet` that lists only the capabilities that each controller operation needs, with the reason for each in the role note.
- The native acceptance tests run every controller operation under the bounded unit.
- An operation that fails under the bound is changed to need less, or its capability is added with its reason; no capability is added without a failing operation that needs it.

## Capabilities

### New Capabilities

- `security/transport-generation-capabilities`: the capability bound of the transport generation controller and the evidence for each listed capability.

### Modified Capabilities

- None

## Impact

- Ansible: the transport-egress unit template and possibly controller operations.
- Tests: the native transport lanes and full-stack Molecule.
- Risk: a missing capability stops frontend recovery; the staging run must cover a reboot.
