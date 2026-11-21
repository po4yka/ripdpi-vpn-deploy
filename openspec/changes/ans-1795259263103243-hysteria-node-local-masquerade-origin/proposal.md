# Change: Serve the Hysteria masquerade site from a node-local origin

Task ID: `ANS-1795259263103243`

## Why

The fleet audit of 2026-11-20 found that the Hysteria masquerade on the UDP node proxies to a host that does not resolve to the node. Change `ans-1795163654691828-udp-node-audit-hardening` added TCP masquerade listeners and refuses a proxy origin on the node's own name, because that origin would request itself. A node without a web frontend therefore still serves a site that another host owns. A probe that compares the site with the address owner can see the mismatch. Hysteria supports a `file` masquerade type that serves a local directory, but no role publishes a site tree on such a node. The operator site bundle of `ANS-1795162466557355` owns site publication, so this change consumes that bundle instead of adding a second content path.

## What Changes

- The Hysteria role can select the `file` masquerade type with a directory that the operator site bundle publishes on the node.
- `vpn-p2-udp` selects the node-local origin when a site bundle is present for the node; the proxy origin stays for nodes without one.
- Admission refuses a `file` origin whose directory is missing, empty or not owned by the publisher.

## Capabilities

### New Capabilities

- `network/hysteria-masquerade-origin`: the choice between a proxy and a node-local masquerade origin, and the admission rules for each.

### Modified Capabilities

- None

## Impact

- Ansible: the Hysteria role and the site bundle consumer. The Hysteria service user needs read access to the published tree.
- Operator: each `vpn-p2-udp` node needs its own site bundle before it can use the node-local origin.
- Dependency: `ANS-1795162466557355` must deliver the per-operator site bundle first.
