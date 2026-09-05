# role: cascade-ingress — client-facing classifier owner

## Design decisions

The role owns the disabled client-termination integration contract and tri-state per-connection classifier adapter. It renders the private egress-leg scaffold but exposes no foreign-facing tunnel listener and has no service-start task. The unchanged SHA256-pinned geodata role output at `geoip.dat` is the only production dataset source. Both the loopback SOCKS adapter and authenticated per-leg probe are installed as implementation artifacts behind literal false systemd execution conditions.

The ingress WireGuard scaffold keeps `AllowedIPs = 0.0.0.0/0` for the future
foreign leg but pins `Table = off`, so bringing up the interface cannot replace
the host default route. Its configuration records the activation contract:
only classifier-owned foreign flows may receive the dedicated mark and routing
table. The repository-disabled scaffold deliberately installs no such rules.

## What's done well

- Dataset preflight runs before the integration contract or tunnel scaffold is rendered.
- The authenticated loopback SOCKS5 CONNECT adapter names all three outcomes and has no fallback; RU and foreign sockets bind to distinct configured interfaces, unsupported UDP is blackholed, WARP coexistence is rejected, and Xray's built-in TCP DNS queries traverse the classifier before domain traffic is handed over as resolved IPs.
- The leg probe requires an authenticated response status and body digest over both the selected leg and an independent direct control, emits only redacted evidence, and cannot run from the repository-owned unit.
- Secret-bearing WireGuard configuration uses `no_log`, `diff: false`, and mode `0600`.
- The nftables namespace is role-scoped and distinct from split-hop.

## Pitfalls

- `dataset-unavailable` is a serving hard-block, never a synonym for `foreign`.
- Dataset generation changes are revalidated before each new connection; missing, empty, corrupt, or concurrently changing data rejects the connection instead of retaining stale classification.
- Do not add a service-management toggle, remove either false execution condition, or enable either timer/service without a reviewed live-authorization decision and live-node evidence.
- The direct and tunnel interfaces must remain distinct; otherwise a default route through the tunnel could make a nominal RU-direct classification egress through the foreign leg.
- Do not import split-hop responder, keepalive, conntrack-direction, or no-listen invariants; they defend a different threat model.
- Egress forwarding/NAT remains outside this implementation-only ingress
  scaffold. Live authorization must add and prove a scoped egress forwarding
  contract; it must not widen the empty ingress table or install a host default.
