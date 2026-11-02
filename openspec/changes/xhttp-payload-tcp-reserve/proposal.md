# Change: Deliver bounded XHTTP pools and payload-verified TCP reserves

Task ID: `XRY-1793635470456809`

## Why

RIPDPI export refuses the existing typed XHTTP pool profile. The recipient can
also lose the pool settings at import. Its payload selector can probe more UDP
candidates before a working TCP reserve after the active UDP path fails.

## What Changes

- Deliver the existing bounded stream-up pool profile to the paired RIPDPI client.
- Share the client pool across sessions for one endpoint and retain its limit.
- Prefer verified TCP reserves after Hysteria2 payload failure, with existing safety bounds.
- Add a generated mixed-transport fixture and positive regression coverage.
- Keep bundle and payload policy version 2. No configuration key is removed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transports/xhttp-alternate-and-tuning`: complete bounded-pool delivery to RIPDPI.
- `clients/payload-aware-failover`: TCP reserve priority after UDP payload failure.

## Impact

Client materialization, selected-recipient fixtures and the paired Android/native
consumer change. Terraform, cloud-init, Ansible runtime roles, public listeners,
engine pins, credentials and live nodes do not change.
