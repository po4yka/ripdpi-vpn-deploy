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
| `vpn-p2-udp.yml` | Hysteria2 + AmneziaWG | default family controls | UDP-only fallback endpoint |
| `vpn-family-standard.yml` | Xray REALITY + nginx-xhttp + Hysteria2 | default family controls | normal family node without AmneziaWG |
| `vpn-device-full.yml` | family-standard + AmneziaWG | default family controls | full device-VPN family node |
| `vpn-device-full-tailnet.yml` | family-standard + AmneziaWG; ordinary OpenSSH over the Tailnet | default family controls | device-full node managed over the Tailnet |
| `vpn-device-full-staging.yml` | device-full transports with transport egress on; monitoring, watchdog and backup off | default family controls | scoped transport and SSH recovery rehearsal, not monitoring or backup acceptance |
| `vpn-split-hop-egress-staging.yml` | none: split-hop egress initiator only, every client transport off | research allowlist `split-hop-egress`; monitoring, watchdog and backup off | disposable staging Node B of the [split-hop pilot](../how-to/split-hop-pilot.md) |
| `vpn-split-hop-ingress-staging.yml` | device-full-staging transports + split-hop responder on UDP/51821 | research allowlist `split-hop-ingress`; monitoring, watchdog and backup off | disposable staging Node A after its first onboarding deploy |
| `vpn-split-hop-family-egress-staging.yml` | as the ingress profile, with every recipient flow routed through Node B | research allowlist `split-hop-ingress`; monitoring, watchdog and backup off | disposable staging Node A for [family egress scope](../how-to/split-hop-pilot.md#6-family-egress-scope) acceptance |
| `vpn-prod-hardened.yml` | device-full | Fail2Ban, tighter SSH limits, egress observation counters | production node when the operator accepts extra host controls |

`vpn-p0-minimal.yml` intentionally leaves `vpn.enable_reality_self_steal` off. Use `vpn-p0-self-steal.yml` only after adding the owned certificate secret contract and changing `xray.target` plus `xray.server_names` together; the role adds a private loopback TLS target without widening the profile's public listener surface.

`vpn-p1-web.yml` disables subscription delivery. Its public surface contains only TCP/80 and TCP/443; device delivery does not open another port on this host.

The separate `vpn-p0-minimal`, `vpn-p1-web` and `vpn-p2-udp` profiles keep monitoring and backup enabled but disable the standalone notification watchdog. Private panel monitoring and provider notifications do not use ntfy or Pushover.

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
echo 'nginx_xhttp_public_site_dir: "/path/to/owned-site"' >> secrets/local/decoy-origin.yml
```

Use an absolute path with safe owner-controlled directories and regular files. Links, hard links, hidden entries and special files are refused. The tree is limited to 1024 entries, 16 path components, 4 MiB per file and 16 MiB in total. The controller uses a private snapshot and rechecks the source before host writes.

A host whose inventory `env` is `prod` refuses convergence while the variable is empty; staging, lab and Molecule hosts may keep the bundled pages.

The same production gate applies to a WireGuard-shaped AmneziaWG instance (`S1 = S2 = 0` with `H1..H4 = 1,2,3,4`): its handshake is a plain 148-byte WireGuard Initiation behind junk. A `prod` host keeps such an instance only when `awg_wireguard_shaped_measurement` names the measurement record (path, date, outcome) that justifies it; put it in the same private override file. The same reasoning applies to `xray.xhttp_path`: the committed example carries a `REPLACE_WITH_` placeholder that strict validation refuses, so choose a private path per deployment.

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
