# Change: Warm the Tailnet management route before readiness and outlast relay home changes

Task ID: `SCR-1795774108061951`

## Why

The operator machine reaches every production node only through a DERP relay: its NAT maps each destination to a different port, and a node accepts inbound Tailscale UDP only for established flows, so no direct path forms ([management route stalls research](../../../docs/research/management-route-stalls-2026-11.md), task `OPS-1795702284251279`). The operator's home relay region changes many times an hour. After each change a node keeps sending to the old region until it learns the new one; on 2026-11-26 node-b dropped every reply to the operator for 96 to 117 s in each such window, and the shared SSH master gives up after 120 s of silence, so three full-graph previews ended after 15 to 25 minutes of work. On 2026-11-27 a preview stopped in its 15 s readiness probe while the operator's client was still connecting to the node's relay region. The route measurement that would establish that connection runs only for `deploy`, and only after the readiness probe.

## What Changes

- Before the readiness probe of a `dry-run` or `deploy` on a Tailnet transport, the controller sends one warm-up `tailscale ping` that waits up to 30 s for a first reply, then measures the route as the deploy gate does today. A route that gives no warm-up reply refuses with `management-route-unreachable` before any SSH command.
- `dry-run` is measured with the same thresholds as `deploy`. This reverses the dry-run exclusion of `REQ-OPS-CHANNEL-GATE` in change `scr-1795082568279731-deploy-slow-channel-tolerance`.
- The shared SSH master that Ansible tasks use keeps a session through 300 s of silence (`ServerAliveInterval=15`, `ServerAliveCountMax=20`) in both modes, instead of 120 s. Ansible SSH retries stay disabled in both modes.

## Capabilities

### New Capabilities

- `operations/management-route-warmup`: warm-up and measurement of the Tailnet management route before readiness in both controller modes, and the shared SSH silence budget.

### Modified Capabilities

- None in the main specifications. The change supersedes the dry-run exclusion of `REQ-OPS-CHANNEL-GATE` and the `ServerAliveCountMax=8` value of `REQ-OPS-CHANNEL-SESSION` in the unarchived change `scr-1795082568279731-deploy-slow-channel-tolerance`; the two are reconciled before either is archived.

## Impact

- `scripts/deploy-controller.py` (route gate placement, warm-up probe, shared master options) and its unit tests; `docs/how-to/deploy.md` for the refusal categories an operator can see.
- No Terraform, Ansible role, secrets or node change. A preview over an unusable route now stops in seconds instead of after minutes; a deploy waits up to 300 s instead of 120 s before a dead node fails its run.
