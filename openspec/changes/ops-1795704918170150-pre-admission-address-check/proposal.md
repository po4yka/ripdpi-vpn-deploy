# Change: Check a new node address from a filtered-side vantage before bundle admission

Task ID: `OPS-1795704918170150`

## Why

Public aggregate data dated 2026-11-24 on VPS-hoster /24 blocks reported about 4 percent of the measured blocks as closed. The report counted a block as closed only when two independent control points failed. The same report said that ICMP toward the gateway understated reachability for one large hoster. Treat both statements as single-source and unverified.

Today a node address reaches a client bundle once the node exists. `make burn-check` then finds a burned address after publication. A node that starts on an unreachable /24 block wastes a bundle cycle and client attempts. The node is disposable, so the cheap fix is to check the address first and recreate the node.

## What Changes

- Add a pre-admission gate. Before a bundle includes a new node address, a TCP and TLS check from a filtered-side vantage must pass.
- When the /24 block of the node fails the check, refuse admission and tell the operator to recreate the node.
- Treat ICMP as a hint only. Document that a missing ICMP result neither proves a tunnel down nor up, and that liveness decisions use authenticated protocol probes.
- Overlap: `make burn-check` observes burn after publication from outside vantages. This gate runs before publication. `fleet-health-rotation` counts authenticated survivors and does not change. `SEC-1793385377599445` repairs REALITY admission and client delivery defects and does not check address reachability.

## Capabilities

### New Capabilities

- `operations/node-address-admission`: pre-admission reachability gate for a new node address.

### Modified Capabilities

- None.

## Impact

- Scripts: the bundle emit path and one new check script.
- Docs: `docs/how-to/deploy.md` and `docs/explanation/threat-model.md`.
- Vantage: reuses the liveness executor mechanism; no new provider resource.
