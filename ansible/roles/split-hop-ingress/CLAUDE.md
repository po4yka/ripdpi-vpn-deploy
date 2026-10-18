# role: split-hop-ingress — Node A responder

## Design decisions

The IPv4 filter guard runs in POSTROUTING. OUTPUT retains its original interface
after route marking, so a later OUTPUT guard can reject valid tunnel traffic.
The final-interface check admits protected IPv4 originals only on loopback or
the tunnel. Protected IPv6 originals are refused in OUTPUT.
The boot policy loader is a required WireGuard dependency. Tunnel PostDown
removes routes only; policy remains active across stop and restart. Explicit
role retirement first requires the canonical firewall to remove its shared
ingress guard, then stops the loader and removes the owned policy. Direct
retirement refuses while that shared guard remains. Check mode skips the live
ruleset refusal because canonical firewall removal is only predicted. Site firewall
publication also retains this boundary before the transport roles run.

Disabled role intent stops only declared owned services and removes exact runtime
configuration; shared packages, immutable release receipts and unrelated state
remain. The unique `split_hop_ingress_role_enabled` selector defaults true for direct calls.

Node A accepts the WireGuard flow initiated by Node B and never configures a peer endpoint or keepalive. Conntrack marks route only new original-direction sockets from the probe Xray and mtg users through the tunnel; replies on accepted client flows keep the public ingress route.

The supported split-hop egress family is IPv4. Node A refuses original-direction
IPv6 packets from the two owned runtime UIDs before marking. Accepted-client
replies and other host users retain their IPv6 behavior. Marked originals leaving
the WireGuard interface are source-translated to A's exact tunnel IPv4, so B's
narrow A/32 peer ACL accepts them and replies traverse the tunnel.

## What's done well

- The responder direction is explicit in the rendered configuration and regression-tested.
- Policy routing is limited to two fixed research runtime UIDs and an isolated nftables table.

## Pitfalls

- Marking every packet owned by the runtime users would also divert client replies and break ingress. Preserve the `ct state new ct direction original` condition.
- Node B must keep `PersistentKeepalive`; removing it reverses the topology signal.
