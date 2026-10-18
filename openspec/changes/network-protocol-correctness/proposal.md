# Change: Repair network protocol correctness audit defects

Task ID: `SEC-1792307003680932`

## Why

The network audit found false-positive safety checks and packet, resolver,
certificate, and browser lifecycle errors. Operators need a complete regression
matrix that separates source acceptance from deployment and device acceptance.

## What Changes

- Match the UpCloud stateless return policy to forwarded NAT traffic.
- Refuse TUN exclusions in a strict full-device kill-switch certificate.
- Check public certificate trust and server purpose for enabled transports only.
- Restore managed DNS stub ownership after DNS-Morph stops.
- Preserve DNS name identity, TCP half-close, and empty UDP datagrams.
- Apply HSTS only when the same public hostname has a compatible HTTPS/443 site.
- Retain the SAN and validity fixes already integrated in PR #328. Accept the
  separately owned Hysteria transit redirect fix only after its source merges.
- Retain the two conditional audit risks as explicit verification gaps.
- Bound checkout discovery after the complete gate confirmed a metadata pipe
  deadlock. Preserve Git filter refusal and path byte identity.
- Correct computed zero UDP checksums in the pinned AWG source build. Bind
  the reviewed source correction to build identity and native regression builds.
- No deployment, credential rotation, new protocol, or runtime version change.

## Capabilities

### New Capabilities

- `security/network-protocol-correctness`: packet and identity preservation,
  strict safety checks, and reversible resolver and browser policy.

### Modified Capabilities

- None. Existing transport profiles and layer ownership remain in force.

## Impact

- Terraform UpCloud edge policy, Ansible baseline and nginx, operator scripts,
  regression tests, snapshots, and operator documentation.
- Coordination with `SEC-1792301529650686` and `SEC-1792306834441683` avoids
  duplicate SAN/validity and Hysteria redirect implementations.
- Public trust verification intentionally refuses privately issued certificates
  unless their issuing CA is already trusted by the operator environment.
