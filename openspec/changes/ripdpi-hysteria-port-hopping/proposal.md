# Change: Deliver native Hysteria port hopping to RIPDPI

Task ID: `OPS-1792820562787120`

## Why

RIPDPI recipient export refuses Hysteria port hopping because the client cannot keep a native QUIC session across destination-port changes. The paired client task supplies that capability. The producer must then retain the admitted hopping policy through export without a partial payload or silent downgrade.

## What Changes

- Permit RIPDPI hopping export after the paired native client passes real-server acceptance.
- Validate the fixed hopping interval and preserve the existing range and interval in both standard fields and RIPDPI extras.
- Keep malformed or conflicting policies fail-closed before publication.
- BREAKING: replace the unconditional RIPDPI hopping refusal with the qualified client contract. Older clients do not satisfy this contract.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `security/audited-delivery-contracts`: admit the complete client hopping profile after positive qualification.
- `operations/deployment-recovery`: export an admitted recipient hopping policy without silent loss.

## Impact

- Client payload production, recipient validation, regression tests, and operator guidance.
- Paired client work: `po4yka/RIPDPI#OUT-1792820412611017`.
- No provider, firewall, credentials, fleet, or production deployment changes.
