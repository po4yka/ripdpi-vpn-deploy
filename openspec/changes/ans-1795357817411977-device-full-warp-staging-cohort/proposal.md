# Change: Add a device-full staging cohort with WARP outbound for refresh acceptance

Task ID: `ANS-1795357817411977`

## Why

SEC-1795260492741288 needs a staging check that the bounded transport generation unit still triggers `ripdpi-warp-refresh.service` and survives a reboot with the WARP backend active. The deploy controller reads the `vpn` toggle map only from tracked cohort files and the extra-vars validator refuses a `vpn` key, while no tracked cohort enables `warp-outbound`. A disposable staging node therefore cannot run the WARP backend at all.

## What Changes

- New family cohort `vpn-device-full-warp-staging`: the `vpn-device-full-staging` map with `enable_warp_outbound: true` and one `warp_outbound_routes` entry (`full:www.cloudflare.com`). A test keeps the two maps equal otherwise.
- Docs name the operator registration step the role leaves to the operator.
- Production profiles and validation are unchanged.

## Capabilities

### New Capabilities

- `ansible/device-full-warp-staging-profile`: a tracked disposable staging cohort that runs the WARP outbound backend on the device-full-staging transports.

### Modified Capabilities

- None.

## Impact

- `ansible/group_vars/vpn-device-full-warp-staging.yml`, `ansible/role-tiers.yml` family list, `ansible/CLAUDE.md`, `docs/reference/deploy-profiles.md`, `docs/reference/architecture.md`, profile tests.
