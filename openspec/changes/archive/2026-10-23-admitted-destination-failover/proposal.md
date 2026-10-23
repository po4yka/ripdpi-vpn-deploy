# Change: Fail over TCP connections across admitted destination addresses

Task ID: `SEC-1792678909985498`

## Why

The guarded normalizer resolves a recipient name but chooses only the lowest
admitted IPv4 address before making one gateway CONNECT request. One unavailable
address therefore fails a request even when another admitted A or AAAA address
can complete it. Preserve the isolation boundary while restoring that positive
TCP capability.

## What Changes

- Race a bounded, family-interleaved set of admitted TCP destination literals
  through the existing fixed native gateway under one connection deadline.
- Commit the first completed SOCKS CONNECT before forwarding application bytes;
  close losing controls and never retry a selected stream after relay starts.
- Retain exactly one resolution/admission snapshot per request and recheck policy
  before each candidate is sent to the gateway.
- Keep UDP's single pinned destination and one-send behavior; this feature does
  not retry datagrams or claim UDP failover.
- BREAKING internal policy API: replace scalar selection with ordered admitted
  candidates and update every consuming caller and test.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transports/resolved-destination-boundary`: bounded TCP connection failover
  across already admitted destination addresses, including IPv4-to-IPv6 fallback.

## Impact

- Ansible-deployed Python runtime helpers: `transport_destination_policy.py` and
  `transport_egress_normalizer.py`; existing private gateway authority is retained.
- Dedicated portable socket tests plus the existing destination-boundary suite.
- No credential, inventory, wire/config schema, Terraform or provider changes.
- No live deployment is part of this implementation or its local evidence.
