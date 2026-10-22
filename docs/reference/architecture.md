# Architecture

> **Status:** Current · **Type:** reference · **Tier:** CORE · **Reviewed:** 2026-10-21

This page is the map: layer ownership, profile-to-role mapping and port
ownership. This repo implements a four-tier multi-profile access stack:

```
P0 Primary       VLESS + REALITY + XTLS-Vision over RAW/TCP/443
P1 HTTPS         VLESS/Trojan + XHTTP behind nginx (direct, no CDN, TCP/8443 by default)
P2 UDP/QUIC      Hysteria2 on UDP/443
P2 Device-VPN    AmneziaWG 2.0 (userspace)
P3 Reachability  Manual — see ../how-to/incident.md (relays, WebRTC, roaming)
P3 Research      Snell v4/v6 candidate (staging only; manual selector)
```

## Layer ownership

| Layer | What it owns | Files |
|---|---|---|
| Terraform | VPS, firewall, SSH key, optional DNS/floating IP | `terraform/providers/<name>/*.tf` |
| cloud-init | Admin user, SSH hardening, python3, marker file | `terraform/shared/cloud-init.yaml.tftpl` |
| Ansible | All runtime state — packages, nftables, xray, nginx, hysteria, awg, monitoring, backup | `ansible/roles/*/` |
| SOPS+age | Secrets at rest | external `~/.config/vpn-provision/` (default) or git-ignored `secrets/local/` |

The boundary is strict: secrets never appear in Terraform state, Terraform
variables, Terraform outputs, cloud-init `user_data`, ansible debug output,
or this repo. Provider credentials live in env vars only.

## Profile-to-role mapping

| Profile | Role | Toggle in `group_vars/all.yml` |
|---|---|---|
| P0 REALITY | `xray` | `vpn.enable_xray_reality` |
| P0 owned REALITY target (optional) | `reality-self-steal` | `vpn.enable_reality_self_steal` |
| P1 XHTTP | `nginx-xhttp` + xray inbound on 127.0.0.1 | `vpn.enable_nginx_xhttp` |
| P2 Hysteria2 | `hysteria` | `vpn.enable_hysteria` |
| P2 AmneziaWG | `amneziawg` | `vpn.enable_amneziawg` |
| P3 Snell candidate | `snell` | `vpn.enable_snell` |

Cross-cutting roles: `baseline`, `firewall`, `monitoring`, `backup`,
optional `subscription-host`.

Deployment profile files make public listener surfaces explicit:

| Profile file | Public transport surface |
|---|---|
| `vpn-p0-minimal.yml` | P0 REALITY only |
| `vpn-p0-self-steal.yml` | P0 REALITY with an owned loopback TLS/H2 target; same public listener surface |
| `vpn-p1-web.yml` | public site + P1 XHTTP on TCP/80 and TCP/443 |
| `vpn-p2-udp.yml` | P2 Hysteria2 + AmneziaWG only |
| `vpn-family-standard.yml` | P0 REALITY + P1 XHTTP + P2 Hysteria2 |
| `vpn-device-full.yml` | family-standard + P2 AmneziaWG |
| `vpn-lab.yml` | lab/pilot surface; research roles require `allow_research_roles` |

Legacy aliases remain for existing inventories: `vpn-p0.yml`, `vpn-p1p2.yml`,
and `vpn-fullstack.yml`.

Default single-host port ownership:

| Port | Owner | Variable |
|---|---|---|
| TCP/443 | P0 REALITY Xray inbound | `xray_port` |
| 127.0.0.1:8443 | Optional P0 owned TLS target, never a public listener | `reality_self_steal_port` |
| TCP/80 | nginx redirect to the public HTTPS site | fixed listener contract entry |
| TCP/8443 | P1 nginx public HTTPS listener | `nginx_xhttp_public_port` |
| 127.0.0.1:10085 | P1 Xray XHTTP local inbound behind nginx | `nginx_xhttp_port` |
| 127.0.0.1:10086 | Xray StatsService, local diagnostics only | `xray_api_listen` |
| 127.0.0.1:9100 | node_exporter including redacted Xray textfile metrics | `monitoring.node_exporter_listen` |
| UDP/443 | P2 Hysteria2 | `hysteria_port` |
| TCP/2443–2445 | P3 Snell evaluation variants | `snell.variants[*].listen_port` |

Direct-only cohorts with REALITY disabled can set `nginx_xhttp_public_port` to
`443`; full-stack hosts must keep the nginx public listener off `xray_port`.

The diagnostic listeners are loopback-only and never enter the public-listener
contract. See `docs/reference/xray-observability.md` for privacy and failure semantics.

The tactical P0 self-steal mode makes the REALITY destination an nginx TLS site on loopback. Enabling it requires `xray.target` to equal `127.0.0.1:<reality_self_steal_port>`, requires the single `xray.server_names` entry to match the SAN of the owned certificate, and does not add TCP/80 or any other public listener. The Xray inbound remains the sole owner of public TCP/443.

## Why it is shaped this way

The reasoning behind disposable nodes, the direct nginx baseline, one Terraform root per provider and the deliberate omissions is in [the architecture rationale](../explanation/architecture-rationale.md); the adversary model is in [the threat model](../explanation/threat-model.md).
