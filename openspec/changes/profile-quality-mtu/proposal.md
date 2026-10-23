# Change: Select profiles by measured transfer quality and diagnose packet size

Task ID: `OPS-1792759217301702`

## Why

A successful handshake or short URL request does not establish useful transfer
quality. The current recipient selector can retain a slow but reachable member
and does not compare verified goodput or latency while data is transferred.
Operators also need packet-size evidence that distinguishes a configured MTU
from a measured lower bound on a specific network path.

## What Changes

- Extend the existing opt-in payload failover policy with bounded quality
  measurements, a shared traffic budget and stable quality-based selection.
- Measure verified application bytes and unloaded and loaded request latency
  through the candidate's actual transport, retaining all lifecycle and network
  fences. Compare healthy candidates without creating a second selector.
- Expose the measurements, selection reason and budget state in the recipient.
- Reuse the recipient's non-root QUIC packet-size probe for explicit MTU
  diagnosis. Preserve address-family, path and network scope, and distinguish
  an acknowledged lower bound from an exact PMTU or a tunnel MTU recommendation.
- BREAKING: replace payload failover policy version 1 with the coordinated
  version 2 contract. Update the producer, consumer and shared fixtures together.
  Migrate previously persisted health-only recipient policies once without
  accepting obsolete wire input or losing catalog identities.
  Plain sing-box URLTest and bundles without the opt-in policy retain their
  existing behavior.

## Capabilities

### New Capabilities

- `clients/profile-quality-mtu`: coordinated quality policy, measurable recipient
  behavior, scoped MTU diagnosis and positive acceptance requirements.

### Modified Capabilities

- `clients/payload-aware-failover`: the existing selector gains quality-based
  comparison while preserving failure recovery, manual choice and scope fences.

## Impact

- The bundle producer, policy validator, executable contract and reference
  examples change in this repository.
- The paired recipient changes its policy parser, existing candidate probes,
  selector state and diagnostic presentation.
- Measurements use operator-configured static HTTPS objects. No mandatory
  backend, new production dependency, live deployment or credential operation
  is included. AmneziaWG remains outside the existing automatic relay pool;
  packet-size diagnostics do not change its configured MTU.
