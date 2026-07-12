# Deploy profiles

Deploy profiles are `ansible/group_vars/vpn-*.yml` files that define the
transport surface and host-hardening posture for a cohort. New hosts should use
an explicit profile rather than relying on inherited `all.yml` defaults.

## Family profiles

Family profiles are listed in `ansible/role-tiers.yml` under
`family_profiles`. The deploy-profile guard treats them as production-safe
surfaces and fails if any RESEARCH-tier role becomes enabled.

| Profile | Transport surface | Hardening posture | Use case |
|---|---|---|---|
| `vpn-p0-minimal.yml` | Xray REALITY only | default family controls | smallest P0 endpoint |
| `vpn-p1-web.yml` | public HTTP/HTTPS site + nginx-xhttp on TCP/443 | default family controls | domain-facing P1 endpoint |
| `vpn-p2-udp.yml` | Hysteria2 + AmneziaWG | default family controls | UDP-only fallback endpoint |
| `vpn-family-standard.yml` | Xray REALITY + nginx-xhttp + Hysteria2 | default family controls | normal family node without AmneziaWG |
| `vpn-device-full.yml` | family-standard + AmneziaWG | default family controls | full device-VPN family node |
| `vpn-prod-hardened.yml` | device-full | unattended security updates, Fail2Ban, tighter SSH limits, egress observation counters | production node when the operator accepts extra host controls |

`vpn-p0-minimal.yml` intentionally leaves `vpn.enable_reality_self_steal` off. Operators may enable this tactical mode only after adding the owned certificate secret contract and changing `xray.target` plus `xray.server_names` together; the role adds a private loopback TLS target without widening the profile's public listener surface.

## Hardened production profile

`vpn-prod-hardened.yml` intentionally keeps the same transport contract as
`vpn-device-full.yml` while changing host hardening. It enables:

- `security_controls.unattended_upgrades=true` through the `package_updates`
  role. The role does not configure automatic reboots.
- `security_controls.fail2ban=true` through the `intrusion_prevention` role.
  Fail2Ban uses nftables sets owned by the firewall role.
- Stricter SSH posture: `RequiredRSASize 3072`, `MaxSessions 1`, and lower
  `MaxStartups`.
- `firewall_egress_policy=logged`, which adds observation counters without
  default-dropping transport egress.

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

## When not to use it

Use `vpn-device-full.yml` instead when you are debugging a new node and want the
least moving parts. Use `vpn-prod-hardened.yml` once the transport surface is
stable and you want the host-level controls to be part of the production
contract.
