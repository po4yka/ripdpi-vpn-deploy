# role: firewall — nftables, scoped to known ports

## Design decisions

**nftables, not ufw/iptables** — single rendered file at `/etc/nftables.conf`,
managed by `templates/nftables.conf.j2`. ufw is too coarse-grained for the
multi-profile stack; raw iptables is too easy to leak state.

**Allow-list only** — explicit accepts for SSH (effective port, not always 22),
P0 (`xray_port` 443/tcp), P1 (`nginx_xhttp_public_port`), P2 (`hysteria_port`
udp). Default policy drop.

**Public listener ports come from Terraform's contract** — `site.yml` verifies `public_listener_contract` against the runtime manifest before this template renders. Do not add transport ports directly to `nftables.conf.j2`.

**Egress modes are opt-in** — `firewall_egress_policy: permissive` preserves
the historical output-chain `policy accept`. `logged` adds counters only, and
`strict` changes host-originated egress to default-drop while preserving
enabled transport data-plane needs.

**AWG forwarding is uplink-scoped** — the forward chain is always default-drop. New packets may only move from an AWG interface to `firewall_awg_uplink_interface` (or the fact-derived default route interface); reply packets use `established,related`. Never restore a broad forward `policy accept`.

**Geo blocking is optional** — `vpn.geo_block` toggles the geo set; default
is on. Geo set is sourced from MaxMind via the `geodata` role.

**Dependent sets apply synchronously** — a rendered firewall config is
reloaded before roles that pre-flight firewall-owned nftables sets run in the
same play. Deferred handlers would make a first toggle fail against stale
runtime state.

## What's done well

- **Cleanup limited to known ports** — when toggling features (disabling
  hysteria, e.g.), the role removes only its own previous rules. Never
  `iptables -F`.
- **`sshd -T`-derived SSH port** — the firewall opens the *effective* SSH
  port read from sshd, not the hard-coded 22. Custom-port operators cannot
  lock themselves out.

## Pitfalls

- **`ufw` is not installed by us, but VPS images may pre-install it** — if
  it's enabled, our nftables ruleset is masked. The role disables `ufw` (and
  warns) before applying nftables.
- **`iptables-nft` shim packages clash with native nftables** — Debian 11
  uses `iptables-nft` by default; Debian 12 ships `nftables` directly.
  Don't mix — the role pins the legacy iptables-nft shim away on D12+.
- **Concurrent `nft` writes corrupt the ruleset** — apply via atomic file
  swap + `nft -f`, not by piping individual rules. The template handler does
  this correctly; don't bypass it.
- **Hysteria UDP port reuse** — if a host enables both Hysteria2 and AWG, do
  not put both on UDP 443 — only the first listener will bind. Pick distinct
  ports or disable one.
- **Strict egress is not a privacy boundary for proxy traffic** — enabled
  proxy transports need broad upstream egress to carry client traffic. Use
  strict mode to constrain host services, not to classify client destinations.
