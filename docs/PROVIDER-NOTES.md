# Provider notes

## ASN / hoster risk tiers (RU threat model, 2026-05)

Source: repository-local deployment measurements and operator validation.

| Tier | Provider / ASN | Notes |
|---|---|---|
| Avoid | Cloudflare AS13335 | TSPU peering at DME/KJA/LED; 8–16 KB cut; see `CDN-DECISION.md` |
| Avoid | OVH AS16276, Hetzner AS24940, DigitalOcean AS14061 | "Foreign datacenter" ASN bucket triggers TCP freeze (~14–25 KB on mobile RU) |
| Avoid | JustHost AS26383, VDSina AS216071 | Frequently flagged as VPN-tenant ranges; high churn |
| Acceptable | UpCloud (current primary) | Not on the public RKN/TSPU watch lists as of 2026-05; verify ASN before rollout |
| Unmeasured | Scaleway | Independent provider root is implemented, but no repository-local filtered-path baseline exists yet; verify the assigned IP and ASN before rollout |
| Preferred | Hostkey, nuxt.cloud (DE/NL), hostvds.com (FI) | Smaller, less-flagged ranges per community testing |
| Jurisdiction-Exception (opt-in only, never Preferred/Acceptable) | *(no provider/ASN preselected — see note)* | RU-hosted cascade entry node for temporary whitelist-riding only. No brand/ASN is listed here on purpose: eligibility is a per-ASN empirical, expiring, fail-closed attestation, never a brand assumption (Yandex.Cloud LLC vs YANDEX LLC are distinct ASNs). First hosting-jurisdiction exception in this repo; accepts bounded RU legal/data-retention/seizure exposure for a temporary node. See `RU-CASCADE-DECISION.md` + `CASCADE-ASN-ATTESTATION.md` + the EXCEPTION tier in `ROLE-TIERING.md` |

For a full deploy this primarily affects the **egress** IP, not the
ingress: a node that ingresses on REALITY/TCP and egresses through the
same VPS IP will hit the TCP-freeze rule when the upstream is on one of
the "Avoid" ASNs. Split-hop egress (separate exit IP, e.g. via WARP) is
documented in `docs/ARCHITECTURE.md` once that role lands.

## UDP/443 edge reachability (Hysteria2 / P2)

Source: repository-local transport validation.
(RCQ, 2026-05-27).

All four provider roots open exactly the typed `public_listeners` contract at the edge firewall, with IPv4 + IPv6 parity. The contract is checked against the runtime listener manifest before deployment:

| Provider | Resource enforcing `public_listeners` | Parity |
|---|---|---|
| UpCloud | `upcloud_firewall_rules.vpn` dynamic `firewall_rule` (`v4`,`v6`) | yes |
| Hetzner | `hcloud_firewall.vpn` dynamic `rule` (`source_ips = 0.0.0.0/0, ::/0`) | yes |
| Vultr | `vultr_firewall_rule.tcp_public` over `public_networks` (`v4`,`v6`) | yes |
| Scaleway | `scaleway_instance_security_group.vpn` dynamic `inbound_rule` (`0.0.0.0/0`,`::/0`) | yes |

**The gap is not a missing rule — it is silent edge drop.** On ≥2 of 4 cloud
providers the KB source tested, inbound UDP/443 is dropped by the
**provider-edge** firewall even when the rule is applied, the instance's own
`nftables` shows ACCEPT, and the listener is bound. The instance kernel cannot
see this layer, so on-host checks (`nft list`, `ss -ulnp`, `iptables -L`) all
look correct while the datagram never arrives.

Diagnostic rule: **trust `tcpdump` showing inbound packets, not `nft list`
showing ACCEPT.** Verification chain after a deploy:

1. Listener bound — `ss -ulnp` shows hysteria on `:443` (the in-host smoke-test
   already dials it from localhost).
2. External probe — `make burn-check` sends an unauthenticated QUIC
   Version-Negotiation trigger from the operator vantage to `UDP/443` and
   treats any reply as proof of end-to-end delivery (non-fatal WARN otherwise).
3. If the probe gets no reply, `tcpdump -i any udp port 443` on the server
   disambiguates: **zero inbound packets ⇒ the provider edge is dropping UDP.**

**Deploy-time manual step when the edge drops UDP despite the rule.** None of
the provider roots require a UI action to *declare* the UDP/443 rule —
all accept it through Terraform. But if the burn-check UDP probe fails while
TCP/443 succeeds, the provider network is dropping UDP at a layer Terraform
cannot reach. The fix is provider-side and manual: open/confirm UDP/443 in the
provider's web console security group, or file a support request to lift a
UDP-default-closed policy. Do not chase the on-host firewall — it is not the
cause. (Note Hysteria2 also supports a non-443 UDP port via `hysteria_port`;
moving to e.g. UDP/8443 sidesteps both edge friction and RU QUIC-throttling on
UDP/443.)

## UpCloud (primary, v1)

UpCloud is the primary provider in v1. Resource shape:

- `upcloud_server` — the VPS itself, with `template { … }` cloning a public
  storage template UUID into the root disk.
- `upcloud_firewall_rules` — attached to the server. Note that UpCloud's
  firewall is on the hypervisor, not the OS — so even if `nftables` is
  misconfigured, UpCloud's rules apply first.
- `network_interface { type = "public" }` + `{ type = "utility" }` are
  required for the server to be reachable; `private` interfaces are
  optional for multi-VPS networking (out of scope for v1).
- Daily snapshots are enabled in `template.backup_rule` (7-day retention).
  This is a hypervisor-level safety net **separate from** restic backups,
  which contain the configs you can restore onto a fresh VPS.

### Useful UpCloud zones for EU baseline

- `fi-hel1` — Helsinki (default in `prod.tfvars.example`)
- `de-fra1` — Frankfurt
- `nl-ams1` — Amsterdam
- `pl-waw1` — Warsaw

#### Zone selection by client cohort

Zone choice is primarily a routing-quality decision, with a secondary
attribution-risk axis. The combination of the IP's prefix-history
weight and the geographic distance to the cohort matters more than the
nominal latency number.

| Cohort | Recommended | Avoid | Why |
|---|---|---|---|
| Mobile-CGNAT cohort | a low-latency zone | a repeatedly probed zone | Prefer the route with lower measured interference, then retain a dissimilar warm spare |
| Residential fixed-IP cohort | a low-jitter zone | a repeatedly probed zone | Validate the assigned prefix and measured XHTTP/Hysteria performance before adoption |
| TLS-policing cohort (~12 connections) | any zone + `xray_flow_mode: mux` | a single untested zone | Mitigation is the cohort-level mux flag (see `docs/MULTI-COHORT.md`), not a location label |
| Development cohort | a low-latency zone | n/a | Development is not the same threat surface as production cohorts |
| Mixed-cohort fleet | two independently measured zones | one zone | Keep a warm spare on a route with different measured behaviour |

After the zone is picked, validate the actual ASN that UpCloud assigns
your VPS prefix:

```bash
make probe-asn HOST=$(PROVIDER=upcloud ENV=prod ./scripts/terraform-env.sh output -raw server_ipv4)
```

If the returned ASN is in the "Avoid" tier from the table at the top of
this document, blue-green immediately to a new IP in the same zone or
move to a different zone. Don't deploy clients against an IP whose ASN
shows up on the TCP-freeze list.

### Storage template UUIDs

UpCloud rotates template UUIDs as new minor versions ship. Always pin a
specific UUID in `tfvars`, never a slug. List candidates with:

```bash
upctl storage list --public --template
```

Pick the most recent Debian 13 or Ubuntu 24.04 minimal cloud image.

### Provider auth

```bash
export UPCLOUD_USERNAME='vpn-deploy'   # sub-account, not master
export UPCLOUD_PASSWORD='…'
```

Use a sub-account with only the rights this stack needs. Never bake
credentials into `*.tfvars` — the provider reads them from env.

Keep provider credentials in an ignored, local environment file or the
operator's secret store, readable only by the current operator (`0600` for a
local file). After creating or replacing a credential, first run the relevant
scoped Terraform plan and confirm it can refresh provider state. Do not put a
token in a command line, a `tfvars` file, state, output, or log.

### Limits to be aware of

- Hypervisor firewall has a per-server rule cap. The base 5–7 rules from
  `firewall.tf` are well within it; if you add per-CIDR carve-outs to the
  point of dozens, watch the cap.
- Object storage / "Managed Database" features are out of scope here.
- API rate limit: low, but Terraform's default backoff handles it.

## Hetzner (v1.1)

Uses:

- `hcloud_server`, `hcloud_ssh_key`, `hcloud_firewall`,
  `hcloud_firewall_attachment`, and optional `hcloud_floating_ip`
  for the honeypot secondary IPv4.
- ASN AS24940 — flagged in the TCP-freeze rule on RU mobile networks
  (see the "Avoid" tier above). Hetzner remains useful for non-RU-mobile
  cohorts and for development; rotate IPs more aggressively than UpCloud.
- Cheaper than UpCloud per spec; smaller geographic surface (EU-heavy +
  US East/West, no APAC).
- IPv6 is enabled by default via `enable_ipv6 = true`; set it false in
  `tfvars` only for regions or plans where you explicitly do not want it.
- Credentials come from `HCLOUD_TOKEN`.

## Vultr (v1.1)

Uses:

- `vultr_instance`, `vultr_ssh_key`, `vultr_firewall_group`,
  `vultr_firewall_rule`, and optional `vultr_instance_ipv4`
  for the honeypot secondary IPv4.
- Wider region coverage than UpCloud / Hetzner.
- IP reputation is more variable; rotate regions when burn-check shows
  a region's prefix is RKN-blocked.
- The provider schema requires an API key in provider config. This root maps
  sensitive variable `vultr_api_key`; export `TF_VAR_vultr_api_key` instead
  of writing tokens into tfvars.
- If an API access allowlist is enabled, admit the operator's current egress
  address before the first plan. Validate a replacement key with a scoped
  plan before revoking its predecessor; a failed plan is not provider-state
  evidence.
- Optional secondary IPv4 allocation uses the provider's reboot path. After apply, `render-inventory.sh` blocks until the address appears on a guest interface over the primary SSH endpoint; API allocation alone is not sufficient evidence for publishing `honeypot_listen_addr`.

## Scaleway (v1.2)

Uses:

- `scaleway_instance_server`, explicit routed `scaleway_instance_ip` resources, and one stateful `scaleway_instance_security_group` generated from `public_listeners`.
- European zones are allowlisted in `variables.tf`; the examples use `pl-waw-1`, but the assigned route must be measured before client rollout.
- Credentials and project selection come from `SCW_ACCESS_KEY`, `SCW_SECRET_KEY`, and `SCW_DEFAULT_PROJECT_ID`.
- The root is operationally supported but censorship-path status remains unmeasured until the filtered-vantage reachability matrix is recorded.
- Provider-managed snapshots are not configured by this root; backups remain owned by the encrypted restic+age path.

## P4 fallback transport tier

The Ansible role `dns-morph-bridge` adds a bootstrap-channel listener
on UDP/53 — a fallback tier beyond P0–P2 used when transport-layer
discovery is itself being interfered with. Operational profile:

- **Port:** UDP/53, public listener (must be allowed inbound on the
  provider's hypervisor firewall — UpCloud/Hetzner/Vultr/Scaleway all default
  to closed; add an explicit allow rule in the provider's tfvars).
- **Co-residency:** non-colliding with P0 (TCP/443), P1 (TCP/8443),
  P2 (UDP/443, UDP/cohort). Safe to enable alongside the full stack
  on a single VPS.
- **Active-probing defense:** the role co-installs `unbound` bound to
  `127.0.0.1:5353`. Any query the bridge does not recognise as a
  handshake fragment is forwarded verbatim so the listener responds
  like a normal recursive resolver under probe.
- **Reflection-attack posture:** unbound refuses recursion for every
  source outside `127.0.0.0/8`. The listener is not an open resolver.
- **Operational noise:** UDP/53 attracts indiscriminate scanner
  traffic. The role caps the active-probing-defense path via
  `dns_morph_bridge.events_per_minute_max` (default 5000/min) to keep
  log volume bounded.
- **Provider compatibility:** any provider that allows arbitrary UDP
  inbound rules. UpCloud and Hetzner accept UDP/53 in their hypervisor
  firewall; Vultr requires an explicit rule on the firewall group.

The role's binary is operator-supplied (`dns_morph_bridge_secrets.
binary_url` + `.binary_sha256`); no public release artifact exists.
Build on a trusted workstation and publish to an internal artifact
store before enabling. See `ansible/roles/dns-morph-bridge/CLAUDE.md`
for the per-role design notes.

## P5 rendezvous transport tier

The Ansible role `hysteria-realm` adds a sing-box realm-service inbound
that mediates UDP-hole-punching handshakes between two peers. The VPN
data plane never touches this VPS — only the small TLS-wrapped
rendezvous handshake. Operational profile:

- **Port:** TCP/`hysteria_realm.listen_port` (default 8444). The realm
  flow is TLS-wrapped because the handshake payload is small enough to
  ride any TLS server, which buys ASN-blocklist resistance.
- **Co-residency:** non-colliding with P0 (TCP/443), P1 (TCP/8443),
  P2 (UDP/443, UDP/cohort), P4 (UDP/53). Collides with the
  subscription-host default port (8444) — operators that enable both on
  the same VPS must override one.
- **Sing-box version pin:** realm-service ships on the alpha line.
  `hysteria_realm.version` is pinned in `defaults/main.yml`; the
  matching tarball sha256 is in `hysteria_realm_secrets.linux_*_sha256`
  so a version bump touches the secrets file only. Both peer sides
  must run sing-box ≥ the pinned tag — asymmetric deployment against
  mainline `apernet/hysteria` is not yet supported upstream.
- **Auth-token discipline:** a single pre-shared `auth_token` mediates
  every handshake. Rotation invalidates every peer; treat it as
  long-lived and rotate only on compromise.
- **TLS material:** with `share_hysteria_tls: true` (default) the role
  symlinks the P2 hysteria role's cert/key into this role's config dir;
  one renewal path covers both tiers.
- **Provider compatibility:** any provider that allows arbitrary TCP
  inbound rules. UpCloud/Hetzner/Vultr/Scaleway all accept TCP/8444 in their
  hypervisor firewall once the Terraform provider opens it.

The role's `MemoryDenyWriteExecute=true` lockdown depends on sing-box
remaining a static Go binary — verify before any future upstream switch
to a runtime that JITs.

## What every provider root must export for inventory compatibility

`scripts/render-inventory.sh` reads exactly these Terraform outputs:

- `server_ipv4` — required
- `server_ipv6` — optional, may be `null`
- `honeypot_ipv4` — optional, may be `null`
- `admin_user` — required
- `server_hostname` — required

Provider roots that don't export these names will need a parallel branch in
the script. Keep the names identical to avoid that.
