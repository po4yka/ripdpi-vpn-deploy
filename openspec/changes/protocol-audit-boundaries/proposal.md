# Change: Repair protocol identity and delivery boundaries

Task ID: `SEC-1792301529650686`

## Why

The protocol audit found eight input and delivery defects. Accepted device
identities can alias, AWG peer addresses can collide with another server
interface, and credentials can change during JSON rendering. Subscription
links, Hysteria recipient admission, per-host metadata and certificate name
checks also disagree with their consumers. Unmatched subscription requests
can expose bearer paths through inherited logging.

## What Changes

- Protect all subscription request outcomes with categorical logging.
- Generate import links for the existing subscription endpoint.
- Refuse VLESS authentication aliases and cross-instance AWG address conflicts.
- Preserve exact Snell and Trojan credential bytes through JSON rendering.
- Refuse unsupported RIPDPI Hysteria hopping delivery before publication.
- Retain Hysteria extension metadata for every emitted host.
- Verify certificate SAN names with the native certificate matcher.
- Add regression tests for each boundary and keep all existing safety gates.
- BREAKING: ambiguous identities and conflicting addresses now refuse admission;
  unsupported RIPDPI hopping artifacts now refuse emission.

## Capabilities

### New Capabilities

- `transports/audit-boundaries`: exact identity, credential, address and recipient
  admission, plus bearer-safe delivery and certificate name validation.

### Modified Capabilities

- None. Existing protocol and deployment contracts remain in force.

## Impact

- Ansible templates, shared validators and client materialization, the vpnd share
  URL builder, and their portable/native regression tests.
- No new dependency, runtime pin, listener, schema field or client implementation.
- No deployment, credential rotation, PQE adoption, AWG backend selection or
  expansion of Realm, multiplexing or arm64 support.
