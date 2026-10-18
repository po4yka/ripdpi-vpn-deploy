# Change: Repair confirmed transport audit boundaries

Task ID: `SEC-1792306834441683`

## Why

Transport combinations can redirect unrelated UDP, lose client options, admit invalid wire parameters or bypass the split-hop route when its tunnel stops. Documentation also overstates negotiated bandwidth and research runtime evidence.

## What Changes

- Scope hopping to local public ingress and preserve metadata for every endpoint.
- Retain a split-hop direct-egress boundary across tunnel stops and admit exact enabled overlay egress in strict mode.
- Match AWG admission to its pinned engine, validate DNS-Morph before host changes, and publish the armored WARP key with its correct suffix.
- Emit supported official-client bandwidth hints and document the RIPDPI capability limit and per-connection negotiation.
- Add regression coverage and correct operator instructions. Invalid configurations that previously passed will now refuse. No public CLI is removed.

## Capabilities

### New Capabilities

- `network/transport-audit-boundaries`: Preserve transport boundaries across composition, export and invalid inputs.

### Modified Capabilities

- None.

## Impact

- Ansible firewall, split-hop, DNS-Morph and WARP roles; shared parameter admission, client exports and liveness; secrets schema and synthetic fixtures.
- No provider changes, real credential operations, runtime rollout or client repository edits.
