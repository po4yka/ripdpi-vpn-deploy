# role: firewall — nftables, scoped to known ports

## Design decisions

**nftables, not ufw/iptables** — single rendered file at `/etc/nftables.conf`,
managed by `templates/nftables.conf.j2`. ufw is too coarse-grained for the
multi-profile stack; raw iptables is too easy to leak state.

**Allow-list only** — explicit accepts for SSH (effective port, not always 22),
P0 (`xray_port` 443/tcp), P1 (`nginx_xhttp_public_port`), P2 (`hysteria_port`
udp). Default policy drop.

**Tailnet SSH is interface-separated** — exact approved `tailscale0` sources
are accepted first, then every other SSH packet on that interface is dropped
before the public CIDR allowlist. Keep that drop even when the Tailnet role is
disabled because a stale interface can outlive its inventory toggle. The live
listener verifier requires the exact accept/drop/public ordering.

**Empty Tailnet sets omit `elements`** — nftables rejects `elements = { }`.
The checked-in empty fragment, inline check-mode render, validator, and guest
transaction helper must keep the same schema-1 bytes.

**Public listener ports come from Terraform's contract** — `site.yml` verifies `public_listener_contract` against the runtime manifest before this template renders. Do not add transport ports directly to `nftables.conf.j2`.

**Egress modes are opt-in** — `firewall_egress_policy: permissive` preserves
the historical output-chain `policy accept`. `logged` adds counters only, and
`strict` changes host-originated egress to default-drop while preserving
enabled transport data-plane needs.

**AWG forwarding is uplink-scoped** — the forward chain is always default-drop. New packets may only move from an AWG interface to `firewall_awg_uplink_interface` (or the fact-derived default route interface); reply packets use `established,related`. Never restore a broad forward `policy accept`.

**AWG NAT is evidence-addressable** — each masquerade rule owns a stable `awg-nat-<interface>` comment and counter. Recurring real-VPS tests consume only that counter; preserve the comment when changing rule shape.

**Geo blocking is optional** — `vpn.geo_block` toggles the geo set; default
is on. Geo set is sourced from MaxMind via the `geodata` role.

**Dependent sets apply synchronously** — a rendered firewall config is
reloaded before roles that pre-flight firewall-owned nftables sets run in the
same play. Deferred handlers would make a first toggle fail against stale
runtime state.

**Echo limits precede conntrack** — established echo streams must still hit
the excess-packet drop. NDP uses hop-limit 255; only router advertisements
require a link-local source, since neighbor discovery includes DAD from `::`.

**Reviewed exposure is validated before mutation** — `network-exposure-gate`
revalidates signed controller artifacts for direct role calls as well as site
deploys. Only an explicitly promoted plan adds directional rules; empty plans
preserve baseline bytes. The rule-bearing render is no_log with diff disabled.

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
- **Task-level check mode has no magic flag** — Ansible's `check_mode: true`
  does not set `ansible_check_mode`. Test-only role inclusion must set the
  explicit `_firewall_task_check_mode` context so validation follows the same
  branch as a real `ansible-playbook --check` run.
