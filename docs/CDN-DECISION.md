# ADR — Cloudflare CDN is not the filtered-network baseline

**Date:** 2026-05-10
**Last reviewed:** 2026-05-11
**Status:** accepted
**Scope:** P1 fallback (`nginx-xhttp` role)

## Evidence anchor

Internal measurements show that a CDN path can share the same filtering
boundary as direct traffic. The observed mechanism is SNI + IP blocking with
an 8–16 KB byte-threshold cut (`/cdn-cgi/trace` passes; full page loads do
not).

## Decision

The `nginx-xhttp` role deploys a **direct foreign VPS** with nginx fronting
443/tcp and proxying a path to the Xray XHTTP inbound on `127.0.0.1`. No
CDN by default.

## Context

A Cloudflare-fronted P1 fallback used to be a sensible recipe (Full
strict TLS, Origin CA, `CF-Connecting-IP` real-IP restoration,
Authenticated Origin Pulls). That recipe is **technically correct** but
**no longer the right default for the filtered-network threat model** as of
April–May 2026:

| CDN | Filtered-network status |
|---|---|
| Cloudflare | Reachable through a shared filtering boundary. XHTTP passes but the 16 KB curtain is active. Not an independent path — a DPI-shaped one. |
| Account-bound CDN | Write methods may be unavailable for anonymous accounts; XHTTP packet-up and gRPC can break. |
| Allowlist CDN | Anonymous endpoints may be unavailable. |
| Other regional CDNs | Functional, candidates for closure within weeks. |
| Akamai / CDN77 / Fastly (GET-only) | Work but expensive or narrow. |

Putting CDN in front of P1 in this regime gains nothing (the RU egress is
still through the same filtering boundary) and adds a dependency that can fail or change policy
overnight.

## What this means in code

- `roles/nginx-xhttp/templates/site.conf.j2` ships nginx pointed at a
  public CA cert for the domain you control, listening on 443/tcp/udp,
  proxying the XHTTP path to Xray. No `set_real_ip_from`, no
  `CF-Connecting-IP`, no Origin CA logic.
- `ansible/roles/cdn-front` exists as a separate, opt-in tactical role
for Cloudflare-fronted XHTTP. It is not part of the baseline and
  is gated by `vpn.enable_cdn_front: false` by default.

## When you might still want CDN

CDN is a **tactical** layer, not a baseline. Reach for it when:

- The direct foreign IP is being IP-blocked on a network path (the failure
  shape is "TLS handshake never completes from this network, but completes
  from a different one"), and an independent CDN path is reachable.
- You need short-term cover while rotating to a new VPS IP.
- You explicitly want browser-shaped traffic for a small, monitored
  deployment, and you're comfortable losing it within weeks.

In those cases, the Cloudflare hardening recipe is well-known: Full
strict TLS mode, Origin CA / public CA, `CF-Connecting-IP` real-IP
restoration so rate-limit and log logic see visitor IPs, origin firewall
restricting 443 to the Cloudflare prefixes, optional Tunnel/AOP/secret
header. Treat that as a **separate role** to add later, not a flag flip
on `nginx-xhttp`.

## When NOT to use CDN under any circumstances

- **Account-bound CDN** — can directly attribute the operator and close for non-corporate accounts.
- **Cloudflare as the *only* path** — single point of policy failure.
- **As a "whitelist bypass"** — CDN reachability is not whitelist
  reachability; that's a different layer (P3 — operator-judged, not
  in this repo's automation scope).

## How this is enforced

- The `nginx-xhttp` role has no CDN-specific code paths.
- The `.gitleaks.toml` has no Cloudflare-specific exemptions.
- This document is referenced from `README.md` and `ARCHITECTURE.md` as
  the canonical answer when someone asks "why isn't CDN the default."
- A separate `cdn-front` role exists for operators who deliberately
  want browser-shaped XHTTP via a non-RU CDN PoP. It is off by
  default (`vpn.enable_cdn_front: false`) and physically separate from
  `nginx-xhttp` — turning it on does not flip a flag in the baseline
  vhost. The role configures real-IP restoration from
  `CF-Connecting-IP`, `nftables` origin-firewall sets populated from
  `cloudflare.com/ips-v4` and `cloudflare.com/ips-v6` (rebuilt daily),
  and optional Authenticated
  Origin Pulls. Operators reach for this role for short-term cover
  during an IP-burn rotation or in cohorts where browser camouflage is
  worth the policy-risk dependency.

## Revisit triggers

Re-evaluate this decision if:

- Cloudflare reverses the RU-PoP-via-TSPU situation (re-check the wiki
  page cited under "Evidence anchor" before flipping this decision).
- A non-RU CDN provides documented, stable, non-TSPU paths into RU.
- The threat model changes (e.g., the operator is no longer targeting RU,
  or the operator wants browser camouflage as the dominant property).

Until then, `nginx-xhttp` is direct.
