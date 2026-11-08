# Change: Issue a device privately when the fleet has no subscription publisher

Task ID: `SCR-1794116837161459`

## Why

The production fleet runs P0 REALITY, P1 XHTTP, Hysteria2 and AmneziaWG, and no node enables `enable_subscription_host`. On such a fleet `make device-lifecycle` cannot issue a device: `ripdpi` and `singbox` delivery refuse with `subscription-delivery-needs-publisher`, and `native` delivery refuses every REALITY, XHTTP and Hysteria2 transport. The only way to issue a device would be to open a public subscription endpoint that the owner does not need. The first consumer is `personal-pixel-incy`, whose INCY links come from `make emit-incy` and whose AWG configuration comes from the private artifact.

## What Changes

- When the manifest declares no publisher, `ripdpi` and `singbox` issue and refresh deliver one private recipient artifact with the rendered profile and AWG configurations, `subscription_url: null` and no published grant.
- Such delivery requires an empty expiry, because no publisher can enforce it, and a private output path for issue and refresh.
- Fleets with publishers and native delivery keep their current behavior. Revocation does not change.

## Capabilities

### New Capabilities

- `clients/device-private-delivery`: publisher-less private delivery for `ripdpi` and `singbox` device operations.

### Modified Capabilities

- None.

## Impact

- Scripts: `scripts/device_lifecycle.py`, `scripts/device_lifecycle_io.py`.
- Secrets: the same encrypted device journal; the artifact is access material written through the existing private output path.
- Docs: `docs/how-to/device-lifecycle.md`.
