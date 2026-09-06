# role: split-hop-egress — Node B in the two-VPS split-hop topology

## Design decisions

**Node B initiates the WireGuard tunnel** — `PersistentKeepalive` is set on
the `[Peer]` block, the `[Interface]` block omits `ListenPort`, and the
`Endpoint = <Node A>:port` line is on the [Peer] (not on A's side). That
direction is load-bearing: if A becomes the initiator, A's outbound to B
re-introduces the dual-role flow pattern this role is designed to break.
See `docs/SPLIT-HOP-TOPOLOGY.md` "Two-node architecture".

**Plain WG, not AmneziaWG** — the tunnel sits between two of our own
VPSes; obfuscating its shape would be defense against an adversary we
do not anticipate at the inter-VPS hop. Standard WG is the minimum-
surface tunnel. An AWG-shaped variant can drop in later by swapping
the config template + adding a cohort file.

**Scoped nft table, not global** — Ansible validates the standalone policy
before loading a table named `split_hop_egress`. A transactional nft batch
replaces only that table, independently from wg-quick lifecycle. This does not
preempt the `firewall` role's owned tables; the tables compose. The firewall
role still owns its input filter and NAT tables; this role only adds
postrouting NAT for forwarded traffic.

## What's done well

- **`no_log: true` on the template task** — the rendered config carries
  the WG private key; standard ansible log discipline keeps it out of
  stdout.
- **Pre-flight assert on every required secret** — disabled-by-default,
  but if an operator flips the toggle without filling SOPS the role
  fails closed before touching disk.
- **Idempotent at the systemd level** — `wg-quick@<iface>.service`
  picks up config changes on restart; the handler chain handles the
  reload.
- **Policy load is drift-aware** — Ansible loads the validated policy when its
  file changes, its scoped table is absent, or its observed NAT shape drifts;
  an unchanged converge is a no-op. The JSON shape validator accepts nft's
  versioned metadata and runtime handle fields while requiring one exact NAT
  table, chain and rule.

## Pitfalls

- **Do not set `ListenPort` on Node B's `[Interface]`** — WG-quick will
  bind it, and a passive listener on B inverts the initiator role.
- **`AllowedIPs = node_a_address`, not `0.0.0.0/0`** — B only routes
  A's tunnel IP back through the tunnel. Setting wider AllowedIPs on
  B makes the tunnel a return-path for arbitrary traffic, which the
  topology does not need.
- **Node A is owned by `split-hop-ingress`** — keep the two roles paired. The
  ingress role renders `AllowedIPs = 0.0.0.0/0`, omits `Endpoint` and
  `PersistentKeepalive`, and marks only original-direction sockets from the
  dedicated probe runtime UIDs; do not duplicate that policy here.
- **Sysctl IP forwarding is set globally** — the role enables
  `net.ipv4.ip_forward=1` for the whole host. On a Node B with no
  other forwarding workload this is fine; if Node B ever also runs
  client-facing transports, audit the forward chain in the firewall
  role.
- **Watchdog gap on a partial outage** — when B is down, A's clients
  still complete TLS handshakes with A but lose upstream. The
  existing `watchdog` role has no per-leg health probe yet. ADR
  flags this as an out-of-scope follow-up.
