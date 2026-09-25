# role: firewall — nftables, scoped to known ports

## Design decisions

**nftables, not ufw/iptables** — single rendered file at `/etc/nftables.conf`,
managed by `templates/nftables.conf.j2`. ufw is too coarse-grained for the
multi-profile stack; raw iptables is too easy to leak state.

**Allow-list only** — an explicit accept for SSH (effective port, not always 22);
every other public port is accepted only through the `public_listener_contract`
loop, never by transport variable name. Default policy drop.

**Tailnet SSH is interface-separated** — exact approved `tailscale0` sources
are accepted first, then every other SSH packet on that interface is dropped
before the public CIDR allowlist. Keep that drop even when the Tailnet role is
disabled because a stale interface can outlive its inventory toggle. The live
listener verifier requires the exact accept/drop/public ordering.

**Empty Tailnet sets omit `elements`** — nftables rejects `elements = { }`.
The disabled checked-in fragment stays empty. An enabled first convergence and
check mode both consume the validator's canonical approved-source fragment;
later transactions preserve the already-published fragment. The validator,
role, and guest transaction helper must keep the same schema-1 grammar.

**Public listener ports come from Terraform's contract** — `site.yml` verifies `public_listener_contract` against the runtime manifest before this template renders. Do not add transport ports directly to `nftables.conf.j2`.

**The SSH port is reserved from the contract** — the contract loop accepts without the SSH source restriction, so a TCP listener or range covering the `sshd -T` port would bypass `allowed_ssh_cidrs`. The assert mirrors the template's `port`-before-`port_range` precedence; keep them in step. The role asserts no such entry exists before its first mutation. It is not allowlistable, and it lives here rather than in `site.yml` pre_tasks because the effective port is host state and the full-stack Molecule image gets `openssh-server` only from `baseline`.

**Egress modes are opt-in** — `firewall_egress_policy: permissive` preserves
the historical output-chain `policy accept`. `logged` adds counters only, and
`strict` changes host-originated egress to default-drop while preserving
enabled transport data-plane needs.

**AWG forwarding is uplink-scoped** — the forward chain is always default-drop. New packets may only move from an AWG interface to `firewall_awg_uplink_interface` (or the fact-derived default route interface); reply packets use `established,related`. Never restore a broad forward `policy accept`.

**AWG NAT is evidence-addressable** — each masquerade rule owns a stable `awg-nat-<interface>` comment and counter. Recurring real-VPS tests consume only that counter; preserve the comment when changing rule shape.

**Geo blocking is documented, not implemented** — the firewall role ships no
country-set rules and has no `vpn.geo_block` toggle. The `geodata` role feeds
Xray egress routing and, when the exception-gated cascade-ingress role is
deployed, the classifier's `geoip.dat` preflight — the firewall consumes
neither. Any inbound geo filtering needs a build decision and a real template
change first; do not claim this control until then.

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
  it's enabled, our nftables ruleset is masked. The role disables `ufw` before
  applying nftables.
- **`iptables-nft` shim packages clash with native nftables** — Debian 11
  uses `iptables-nft` by default; Debian 12 ships `nftables` directly.
  Don't mix. The role does not detect or remove an active `iptables-nft`
  shim; only the `ufw` conflict above is guarded, so treat such a host as an
  open risk.
- **Concurrent `nft` writes corrupt the ruleset** — apply via atomic file
  swap + `nft -f`, not by piping individual rules. Publication is two
  steps: the template task's `validate: "nft -c -f %s"` only syntax-checks
  the candidate before the atomic swap, and the later `Reload nftables
  before dependent roles run` task loads it. Keep both; without the reload
  the host keeps running the old rules.
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
- **Fresh check mode cannot activate planned recovery units** — the unit copy
  is simulated before systemd can discover it. Require the exact unit's copy
  task to plan a change, then defer only its service activation; real deploy
  still enables both units.
- **Do not left-trim before nft rule blocks** — `{%- if` can join the first
  conditional rule to the preceding terminal statement under Ansible's Jinja
  whitespace policy. Preserve a real newline before every emitted rule.
