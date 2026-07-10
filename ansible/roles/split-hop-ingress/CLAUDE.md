# role: split-hop-ingress — Node A responder

## Design decisions

Node A accepts the WireGuard flow initiated by Node B and never configures a peer endpoint or keepalive. Conntrack marks route only new original-direction sockets from the probe Xray and mtg users through the tunnel; replies on accepted client flows keep the public ingress route.

## What's done well

- The responder direction is explicit in the rendered configuration and regression-tested.
- Policy routing is limited to two fixed research runtime UIDs and an isolated nftables table.

## Pitfalls

- Marking every packet owned by the runtime users would also divert client replies and break ingress. Preserve the `ct state new ct direction original` condition.
- Node B must keep `PersistentKeepalive`; removing it reverses the topology signal.
