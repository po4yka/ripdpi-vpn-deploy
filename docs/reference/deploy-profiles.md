# Deploy profiles

> **Status:** Current · **Type:** reference · **Tier:** — · **Reviewed:** 2026-11-05

Deploy profiles are `ansible/group_vars/vpn-*.yml` files that define the transport surface and host-hardening posture for a cohort. New hosts should use an explicit profile rather than relying on inherited `all.yml` defaults.

## Family profiles

Family profiles are listed in `ansible/role-tiers.yml` under `family_profiles`. The deploy-profile guard treats them as production-safe surfaces and fails if any RESEARCH-tier role becomes enabled.

| Profile | Transport surface | Hardening posture | Use case |
|---|---|---|---|
| `vpn-p0-minimal.yml` | Xray REALITY only | default family controls | smallest P0 endpoint |
| `vpn-p0-self-steal.yml` | Xray REALITY + owned loopback TLS/H2 target | default family controls; no additional public listener | P0 endpoint after DNS and certificate promotion gates pass |
| `vpn-p1-web.yml` | public HTTP/HTTPS site + nginx-xhttp on TCP/443 | default family controls | domain-facing P1 endpoint |
| `vpn-p2-udp.yml` | Hysteria2 (with its masquerade site over TCP) + AmneziaWG | default family controls | UDP-only fallback endpoint |
| `vpn-family-standard.yml` | Xray REALITY + nginx-xhttp + Hysteria2 | default family controls | normal family node without AmneziaWG |
| `vpn-device-full.yml` | family-standard + AmneziaWG | default family controls | full device-VPN family node |
| `vpn-device-full-tailnet.yml` | family-standard + AmneziaWG; ordinary OpenSSH over the Tailnet | default family controls | device-full node managed over the Tailnet |
| `vpn-device-full-staging.yml` | device-full transports with transport egress on; monitoring, watchdog and backup off | default family controls | scoped transport and SSH recovery rehearsal, not monitoring or backup acceptance |
| `vpn-device-full-warp-staging.yml` | device-full-staging transports plus the WARP outbound backend with one route | default family controls | disposable staging check of the WARP namespace refresh through its own onboarding intent |
| `vpn-p2-udp-staging.yml` | the `vpn-p2-udp` transports and masquerade listeners; monitoring, watchdog and backup off | default family controls | disposable staging dry-run of the p2-udp transport set with staging secrets only |
| `vpn-split-hop-egress-staging.yml` | none: split-hop egress initiator only, every client transport off | research allowlist `split-hop-egress`; monitoring, watchdog and backup off | disposable staging Node B of the [split-hop pilot](../how-to/split-hop-pilot.md) |
| `vpn-split-hop-ingress-staging.yml` | device-full-staging transports + split-hop responder on UDP/51821 | research allowlist `split-hop-ingress`; monitoring, watchdog and backup off | disposable staging Node A after its first onboarding deploy |
| `vpn-split-hop-family-egress-staging.yml` | as the ingress profile, with every recipient flow routed through Node B | research allowlist `split-hop-ingress`; monitoring, watchdog and backup off | disposable staging Node A for [family egress scope](../how-to/split-hop-pilot.md#6-family-egress-scope) acceptance |
| `vpn-split-hop-egress-live.yml` | the staging Node B map plus `enable_liveness_sentinel: true` | research allowlist `split-hop-egress`, `liveness-sentinel`; no client listener, no sentinel service | long-lived Node B of a live research pair, never a family node |
| `vpn-split-hop-ingress-live.yml` | device-full-tailnet transports + split-hop responder on UDP/51821 | research allowlist `split-hop-ingress`; monitoring, watchdog and backup on | long-lived Node A of a live research pair before family scope |
| `vpn-split-hop-family-egress-live.yml` | as the live ingress profile, with every recipient flow routed through Node B; REALITY self-steal on loopback port 8444, so TCP/443 presents the operator certificate | research allowlist `split-hop-ingress`; monitoring, watchdog and backup on | long-lived Node A serving devices through Node B; liveness needs `awg_ipv6: ipv4-only` |
| `vpn-prod-hardened.yml` | device-full | Fail2Ban, tighter SSH limits, egress observation counters | production node when the operator accepts extra host controls |

`vpn-p0-minimal.yml` intentionally leaves `vpn.enable_reality_self_steal` off. Use `vpn-p0-self-steal.yml` only after adding the owned certificate secret contract and changing `xray.target` plus `xray.server_names` together; the role adds a private loopback TLS target without widening the profile's public listener surface.

`vpn-p1-web.yml` disables subscription delivery. Its public surface contains only TCP/80 and TCP/443; device delivery does not open another port on this host.

`vpn-p2-udp` sets `hysteria_masquerade_tcp`, so Hysteria serves its masquerade site on TCP/443 as well as over HTTP/3, and on TCP/80 when native ACME is off. Before the first deploy with this setting, add the listeners to the node's Terraform `public_listeners` and apply: `{ name = "hysteria-masquerade", protocol = "tcp", port = 443, port_range = null }`, and the same entry with port 80 unless the list already has `hysteria-acme` on TCP/80. Without these entries the deploy refuses in the listener contract check before it changes the host. The profile also sets `hysteria_resource_profile_default: bbr-conservative`; a secrets document that states `hysteria.resource_profile` overrides it, so change a stated `bandwidth-capped` (the example value) to `bbr-conservative`; client exports then also stop carrying bandwidth hints.

`vpn-device-full-warp-staging` is the `vpn-device-full-staging` `vpn` map with `enable_warp_outbound: true` and one `warp_outbound_routes` entry; a test keeps the two maps equal otherwise. It also carries the complete `warp_outbound` map with the exact `package_version` pin that the role requires, otherwise equal to the role defaults. Isolated WARP needs systemd 257 or newer, so the node must run Debian 13; Ubuntu 24.04 ships systemd 255 and refuses before any change. A deploy that changes the cohort changes the deployable digest and needs a fresh promotion proof, and only a new disposable onboarding intent binds the executor to the new liveness configuration. So run the switch as a new onboarding: prepare an intent with `PROMOTION_COHORT=device-full-warp-staging` and new output paths, render the inventory with `COHORTS=device-full-warp-staging` and deploy with that intent. The `warp-outbound` role never creates an account, so its first deploy stops at the registration check until the operator registers the vendor client once inside the `ripdpi-warp` namespace (`ip netns exec ripdpi-warp warp-cli registration new`, which accepts the vendor terms); the next deploy then connects the tunnel. Registering creates a vendor account, so it needs the owner's explicit authorization.

`vpn-p2-udp-staging` is the `vpn-p2-udp` `vpn` map with `enable_monitoring`, `enable_watchdog` and `enable_backup` set to `false`; a test keeps the two maps equal otherwise. It needs no watchdog canary, `watchdog` Hysteria client or backup remote, so the secrets that `scripts/ci-bootstrap-secrets.sh` generates are its only secrets input. Its `public_site_canonical_url` is the generated staging origin that the generator also writes to `hysteria.masquerade_url`, so no extra-vars origin is needed. To serve the node's own site bundle, pass `hysteria_public_site_dir` (and the public site inputs it names) in `ANSIBLE_EXTRA_VARS_FILE`. For the dry-run, render the inventory with `COHORTS=p2-udp-staging` and give the staging node's Terraform `public_listeners` the p2-udp entries: `hysteria` UDP/443, `amneziawg` UDP/51820 and `hysteria-masquerade` TCP/443 and TCP/80. `make dry-run` reads no promotion config; a real first deploy of a fresh node still onboards through `device-full-staging`, because the disposable onboarding intent admits only that cohort.

The separate `vpn-p0-minimal`, `vpn-p1-web` and `vpn-p2-udp` profiles keep monitoring and backup enabled. `vpn-p1-web` and `vpn-p2-udp` also run the local watchdog, which probes and recovers their transports and, with the default `watchdog.provider: none`, sends nothing off the node; `vpn-p0-minimal` disables it. The watchdog needs an operator-owned HTTPS canary in `watchdog_secrets.reality_probe_url` and a dedicated probe identity named `watchdog`: an `xray.clients` entry on `vpn-p1-web` and a `hysteria.clients` entry on `vpn-p2-udp`. Private panel monitoring and provider notifications do not use ntfy or Pushover.

Every fleet profile inherits security-only unattended updates from `all.yml`. Automatic reboot remains disabled; use `make os-maintenance` for a serial full upgrade, conditional reboot, and both verification gates.

## Recipient resilience options

These settings do not add listeners to a family profile:

- Optional `xray.xhttp_tuning` selects the [bounded XHTTP pool](xhttp-delivery-profiles.md). It requires `stream-up` and matching recipient support; omission retains the untuned profile.
- `client_payload_failover` defaults to `null`. An explicit [version 2 payload policy](ripdpi-bundle.md#ripdpipayload_failover) requires the paired RIPDPI client and two independent owned HTTPS controls.
- P0 REALITY and P1 XHTTP provide TCP candidates alongside Hysteria2. With the explicit policy, the paired client checks TCP reserves first after active Hysteria2 payload failure. AmneziaWG is outside this selector pool.

Export and validate fresh per-device bundles after selecting these options. The shipped profiles do not activate them or provision control origins. See [the deployment snapshot](deployment-status.md) for observed activation status.

## Hardened production profile

`vpn-prod-hardened.yml` intentionally keeps the same transport contract as `vpn-device-full.yml` while changing host hardening. It enables:

- the baseline `package_updates` policy without changing its no-automatic-reboot contract.
- `security_controls.fail2ban=true` through the `intrusion_prevention` role. Fail2Ban uses nftables sets owned by the firewall role.
- Stricter SSH posture: `RequiredRSASize 3072`, `MaxSessions 1`, and lower `MaxStartups`.
- `firewall_egress_policy=logged`, which adds observation counters without default-dropping transport egress.

It deliberately keeps RESEARCH-tier roles disabled:

- `dns-morph-bridge`
- `hysteria-realm`
- `split-hop-egress`

## How to use

For a three-provider split, copy `.fleet.mk.example` to the ignored `.fleet.mk`. The committed example maps the P0, P2 UDP, and P1 web provider environments to their explicit cohorts, and `make inventory` loads it automatically.

Render inventory with the hardened cohort:

```bash
HOSTS="upcloud:prod" COHORTS="prod-hardened" ./scripts/render-inventory.sh
```

Then run the normal lifecycle:

```bash
make decrypt
make dry-run
make deploy
make verify
make smoke-test
```

## Decoy site identity

Committed profiles carry only the neutral placeholder (`https://vpn.example.com`) for `public_site_canonical_url`. Supply the real decoy origin per deploy through the validated override file (regular, non-symlink, owner-only mode 0600) and deploy only to explicitly limited hosts:

```bash
mkdir -p secrets/local
echo 'public_site_canonical_url: "https://<your-decoy-origin>"' > secrets/local/decoy-origin.yml
chmod 0600 secrets/local/decoy-origin.yml
make dry-run ANSIBLE_LIMIT=<host> ANSIBLE_EXTRA_VARS_FILE=secrets/local/decoy-origin.yml
make deploy ANSIBLE_LIMIT=<host> ANSIBLE_EXTRA_VARS_FILE=secrets/local/decoy-origin.yml
```

The value must be an https origin; convergence fails closed on the `nginx-xhttp` / `hysteria` role asserts if it does not match the site identity in secrets. The dry run reaches those same asserts, so it needs the override too.

The decoy content itself is operator-owned on production hosts. The pages bundled under `ansible/roles/nginx-xhttp/` are committed in a public repository, so every node that keeps them serves one byte-identical identity that a scanner can cluster. Put a complete static site (at least `404.html`; any further files and subdirectories are published at the same relative paths) in a controller-local directory and name it in the same override file:

```bash
echo 'nginx_xhttp_public_site_dir: "/path/to/site-bundle"' >> secrets/local/decoy-origin.yml
```

The value names a site bundle from `make public-site-build` ([how to build one](../how-to/public-site.md)): its `site/` directory holds the static tree (at least `index.html` and `404.html`), and `backlog.tar.gz` with `schedule.json`, when present, let the node publish later generations without a deploy. A production deploy and dry run refuse a bundle that `make public-site-check` refuses. Use an absolute path with safe owner-controlled directories and regular files. Links, hard links, hidden entries and special files are refused. The tree is limited to 1024 entries, 16 path components, 4 MiB per file and 16 MiB in total. The controller uses a private snapshot and rechecks the source before host writes.

A production host is one whose inventory `env` or `vpn_build_environment` is `prod`. `make inventory` writes `vpn_build_environment` from the Terraform `build_env` variable, so a permanent workspace with its own name is a production host too. A production host refuses convergence while the variable is empty; staging, lab and Molecule hosts may keep the bundled pages.

The REALITY self-steal site follows the same contract through `reality_self_steal_public_site_dir`. Its bundle has the same layout; the three pages bundled under `ansible/roles/reality-self-steal/` are refused on a production host and removed where the operator tree does not provide them.

### One TLS identity for each production address

A borrowed REALITY target shows the target's certificate on TCP/443. When Hysteria or nginx-xhttp presents the operator certificate on the same address, one scan finds two unrelated names. A production host refuses that layout before any host change, and also refuses a borrowed target that the validator reported in a different network. The failure message names the listeners. Choose one of these:

| Choice | Input |
|---|---|
| Present the operator certificate on TCP/443 too | `vpn.enable_reality_self_steal: true` with the `reality_self_steal.*` secrets |
| Keep the borrowed target on a node without those listeners, with a target in the node's network | a P0 profile, and `reality_target_network: same_asn` |
| Keep the layout and record why | `tls_identity_exception: "<path, date, outcome>"` |

`reality_target_network` holds the `target_network` value that `NODE_ADDRESS=<node address> make validate-target` reports (`same_asn`, `different_asn` or `unknown`); only `different_asn` refuses. Put both values in the private extra-vars file. The node manifest records `security_controls.tls_identity_exception` as `true` or `false` and never the reason. A host whose `env` is not `prod` is not checked.

The same production gate applies to an AmneziaWG instance in which any of `H1..H4` is a value from 1 to 4: with `H4 = 4` its data packets are plain WireGuard transport messages whatever `S1` and `S2` are, and with `H1 = 1` and `S1 = 0` its handshake is a plain 148-byte WireGuard Initiation behind junk. A `prod` host keeps such an instance only when `awg_wireguard_shaped_measurement` names the measurement record (path, date, outcome) that justifies it; put it in the same private override file. The same reasoning applies to `xray.xhttp_path`: the committed example carries a `REPLACE_WITH_` placeholder that strict validation refuses, so choose a private path per deployment.

### Secrets that rotate together with the origin

Changing the override alone is not enough — the following SOPS keys must be updated to the new domain in the same rotation, or convergence fails (or worse, clients keep the old TLS name):

| Secrets key | Why it must match |
|---|---|
| `nginx_xhttp.server_name`, `nginx_xhttp.cert_pem`, `nginx_xhttp.key_pem` | The p1-web site identity; the nginx-xhttp assert pins `public_site_canonical_url == https://<server_name>` |
| `nginx_xhttp.fallback_server_name`, `fallback_cert_pem`, `fallback_key_pem` | Only when the optional direct fallback serves a distinct domain |
| `hysteria.masquerade_url` | The hysteria assert requires it to equal `public_site_canonical_url` exactly |
| `hysteria.cert_pem`, `hysteria.key_pem` | Hysteria's own TLS certificate must cover the client-facing name |
| Client-facing server name used by emitters (`hysteria.server_name` or, on p1-web, `nginx_xhttp.server_name`) | Emitted clients derive their TLS SNI from it; a stale value keeps old-domain traffic alive after rotation |
| `reality_self_steal.server_name`, `cert_pem`, `key_pem` | Only when REALITY self-steal shares the decoy identity |

Rotating means: register the new domain, issue the certificate, update these keys in SOPS, update the extra-vars override file — never any committed file.

## When not to use it

Use `vpn-device-full.yml` instead when you are debugging a new node and want the least moving parts. Use `vpn-prod-hardened.yml` once the transport surface is stable and you want the host-level controls to be part of the production contract.
