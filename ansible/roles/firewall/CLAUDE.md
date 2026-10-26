# role: firewall — nftables, scoped to known ports

## Design decisions

An AWG device revocation shares the runtime operation/digest. Pending policy ownership permits only that exact forward retry, and neither legacy restoration nor consumer compensation may cross its accepted revocation floor. Failure retains the candidate policy and stopped runtime instead of readmitting the removed peer.

DHCPv6 uses one admitted uplink: an explicit override, then the observed
IPv6 default interface, then IPv4 for initial acquisition. Admission runs before
firewall helper installation and excludes absent, loopback, Tailnet and AWG
interfaces. UDP 547-to-546 replies require a local destination and link-local
source on that interface; strict output permits the inverse port pair to the
local multicast group or a link-local server. Multicast replies do not depend
on reverse conntrack matching. A bounded exact canonical IPv6 server list adds
legacy unicast authority; prefixes and broad global UDP accepts are refused.
Set overrides in reviewed cohort `group_vars`; they are not live CLI overrides.
The default uses observed facts and needs no new operator input.

DHCPv6 scope applies before generic conntrack acceptance. After invalid-state
refusal, scoped replies and strict-output requests pass their exact rules; the
remaining canonical IPv6 client port pair drops before established acceptance.
Conntrack does not retain interface scope, so identical link-local tuples on
different interfaces must remain denied after a valid unicast request/reply.
Legacy server accepts stay bounded and permissive/logged output keeps its policy.

Provider-filtered UpCloud inventory carries `terraform_nat_source_port_range`.
Validate it before mutation and against the effective SSH port. AWG TCP/UDP NAT
uses that exact range; other protocols retain address-only NAT. The primary
`awg-nat-<interface>` counter continues to cover TCP/UDP probes; the separate
`awg-nat-other-<interface>` counter covers other protocols. Disabled provider
filtering and other providers preserve ordinary source-port selection.

Split-hop IPv4 guard rules use POSTROUTING to inspect the final interface after
route marking. OUTPUT can retain the earlier interface. The IPv6 original-traffic
guard remains in OUTPUT before established acceptance; neither guard depends on
the tunnel's lifecycle. Retirement checks both owned canonical chain names.

Hopping REDIRECT matches only default-route ingress interfaces and destinations
classified local by the kernel FIB. Forwarded UDP keeps its destination even
when its port belongs to the hopping range. Strict output retains bounded
Tailnet root UDP allowances (default source 41641 and STUN destination 3478)
and the exact split-hop peer destination. Custom tailscaled socket ports need
a reviewed firewall contract. Enabled split-hop ingress denies protected UID
originals outside its tunnel before conntrack acceptance in every output mode.
The shared guard also follows an explicit false role selector. A direct role
retirement cannot remove firewall-owned rules; converge the canonical disabled
policy first.

Fresh site convergence creates the shared runtime parent before the first retained firewall publication. Admit existing ancestry and the private firewall leaf first; create only an absent parent and preserve existing trusted ownership and mode. The generic publisher still refuses missing or unsafe mutation parents. Check mode predicts creation without creating runtime state.

The inline accepted-policy reader preserves the common source file newline with the file lookup rstrip option. Test the actual Ansible-rendered command; a literal escaped separator can make valid source modules an invalid Python program.

Initial site publication uses only AWG claims read from the exact private instance record and its owned configurations. Desired peer changes wait for the AWG consumer. A tagged run that omits protected consumers refuses a changed public listener contract before publication. The shared publisher retains the initial firewall until the ingress journal records and completes the same durable `committing` decision. It never restores an old firewall after that decision. AWG then uses a separate retained firewall transaction, so its refusal does not undo an already accepted protected frontend. Shared consumer helper ancestry is admitted before file convergence or recovery execution. The operator must retain the existing one-live-deploy-per-node discipline; per-call locks do not grant whole-play concurrency.

AWG candidate activation retains the prior complete firewall file through service
acceptance. Failure restores it atomically before prior tunnels restart, so
changed peer claims cannot strand the restored addresses. A fresh host retains
a canonical default-drop baseline with AWG forwarding disabled. Foreign nft
tables and named timed-set membership remain outside this rollback.
The root-owned executable distro starter is admissible for replacement; its
bytes never become recovery authority. Role-owned retained files must remain
nonexecutable, with mode 0600 or 0644.

AWG forwarding checks both typed source families and denies movement outside
the exact uplink before established conntrack acceptance. Each NAT rule matches
that same uplink; a stale connection cannot authorize cross-instance forwarding.
Empty peer families drop explicitly. Missing IPv6 uplink authority refuses
before firewall publication. Scenario-only public-family routes are confined to
each disposable Molecule namespace. The firewall scenario supplies explicit
typed peer claims on awg7 and checks its exact synthetic uplink; it cannot
fall back to an implicit awg0.


AWG interface names come only from the nonempty canonical instance list; no
legacy `awg0` fallback grants forwarding or backup authority.

Strict output admits untracked IPv6 router solicitation and neighbor discovery only at hop limit 255, plus essential ICMPv6 error reports. It does not permit arbitrary ICMPv6 or outbound echo. Native regression clears both neighbor caches before each HTTPS-port exchange.

**Recipient egress has an independent late guard** — the transport role owns a separate nft table, so this role's scoped filter/NAT reload preserves its active boundary. WARP namespace forwarding is limited to the exact owned veth and source address; the namespace gateway can send plaintext only through a verified TUN ifindex. The transport table owns underlay NAT and refuses private forwarding destinations. Host infrastructure UIDs retain their ordinary firewall policy.

**Hysteria hopping belongs to nftables** — the role redirects the admitted UDP range to the fixed Hysteria listener in the owned inet NAT table. The daemon receives no network-administration capability. Removing the range removes the redirect without affecting AWG postrouting.

**Strict proxy egress includes XHTTP and Snell** — standalone enabled proxy profiles have the same arbitrary upstream allowance as REALITY, Hysteria and Naive; host-only profiles keep their narrow infrastructure allowance.

**nftables, not ufw/iptables** — single rendered file at `/etc/nftables.conf`,
managed by `templates/nftables.conf.j2`. ufw is too coarse-grained for the
multi-profile stack; raw iptables is too easy to leak state.

Provider UFW retirement is shared through `tasks/retire-provider-ufw.yml`.
A first-enrollment caller must admit the exact fresh host, restrictive provider
SSH rules and recovery before this slice. It does not establish Tailnet access.

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

**AWG forwarding shares the recipient destination boundary** — before the
uplink accept, packets from an AWG interface to
`firewall_awg_destination_deny_v4`/`_v6` drop with counters. The defaults equal
`scripts/transport_destination_policy.py` (unit-tested), so AWG devices cannot
reach provider metadata or private ranges that Xray and Hysteria refuse. Native
labs whose public stand-in is ULA override only the IPv6 list.

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

**Rule reloads preserve active enforcement** — the inet filter table is added
idempotently and flushed in the same batch before rules are reimported. Named
Fail2Ban and policy sets retain their kernel membership and remaining expiry;
there is no userspace snapshot race or timeout restart. Disabled sets retire
explicitly. Tailnet source sets are replaced from their owned authority fragment,
and active CDN origin sets retain the prefix refresher's current authority.

## What's done well

- **Cleanup limited to known ports** — when toggling features (disabling
  hysteria, e.g.), the role removes only its own previous rules. Never
  `iptables -F`.
- **`sshd -T`-derived SSH port** — the firewall opens the *effective* SSH
  port read from sshd, not the hard-coded 22. Custom-port operators cannot
  lock themselves out.

## Pitfalls

- The timed-ban Molecule refresh marks only the exact terminal INPUT drop before
  the forward chain. A substring match can add a second comment to a scoped
  DHCPv6 deny. Keep both DHCPv6 comments and the timed-set expiry checks intact.

- The Molecule fixture pins DHCPv6 to its Docker uplink because AWG preparation
  adds an isolated IPv6 default route after the first fact gather. Keep this test
  authority explicit so the second gather cannot change the rendered candidate.

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
- **Timers require systemd load-state discovery** — `service_facts` does not
  enumerate timer units. Check mode queries each recovery unit's `LoadState`
  without mutation; loaded units retain activation checks, while `not-found`
  still requires the exact copy task to plan installation. Failed or unknown
  discovery refuses rather than treating the unit as absent.
- **Do not left-trim before nft rule blocks** — `{%- if` can join the first
  conditional rule to the preceding terminal statement under Ansible's Jinja
  whitespace policy. Preserve a real newline before every emitted rule.
