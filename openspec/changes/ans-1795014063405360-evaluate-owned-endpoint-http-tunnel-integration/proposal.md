# Change: Qualify an owned-endpoint HTTP tunnel adapter

Task ID: `ANS-1795014063405360`

## Why

The baseline has TCP and UDP transports but no TrustTunnel endpoint contract. Its HTTP/2 and HTTP/3 CONNECT protocol offers an independently implemented alternative, not evidence that an unreachable endpoint can pass an IP allowlist. Current repository code and portfolio were searched for TrustTunnel before this proposal.

## What Changes

- Implement an isolated, credential-free qualification harness and an explicit admit/reject report before proposing production integration.
- Compare TCP, UDP and DNS behavior against existing transport acceptance, including HTTP/3 unavailable and HTTP/2 fallback.
- No breaking changes; no deployment, protocol toggle or client bundle addition in this change.

## Capabilities

### New Capabilities

- `owned-http-tunnel-qualification`: reproducible admission evidence for an optional owned endpoint.

### Modified Capabilities

- None.

## Impact

Future Ansible runtime and client bundle work depends on this qualification. Terraform, cloud-init, SOPS secrets, baseline profiles and vpnd remain unchanged. Upstream endpoint and client are Apache-2.0; exact revision and dependency obligations must be recorded before fixture execution.
