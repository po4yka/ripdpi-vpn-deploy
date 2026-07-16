# role: nginx-xhttp — P1 HTTPS path

## Design decisions

**Direct only by default** — `vpn.enable_cdn_front` is false in baseline.
The role ships nginx pointed at a public CA cert for the operator's domain,
listening on `nginx_xhttp_public_port` (default 8443), reverse-proxying the
XHTTP path to Xray on `127.0.0.1:10085`. No `set_real_ip_from`, no
`CF-Connecting-IP`, no Origin CA. Rationale: `docs/CDN-DECISION.md`.

**Ordinary paths are a real static site** — the role publishes repository-owned content to `/var/www/public-site`, serves it on the primary and alternate HTTPS vhosts, and redirects TCP/80 to the configured HTTPS port. Identity pages are rendered from `templates/public-site/` so canonical metadata follows `public_site_canonical_url`; reusable CSS, favicon, search logo, and the host-neutral 404 remain static files. The secret XHTTP path remains a separate exact transport seam. Keep admin, metrics, status, and health endpoints off the public vhost.

**One search identity graph** — `LLM Model Notes` is the sole public name. The home page emits `WebSite` + `Organization`; supporting pages emit `WebPage`; articles emit `Article` with the same visible author/publisher and dated metadata. Stable entity IDs, logo URLs, canonicals, Open Graph URLs, and the lowercase domain fallback all derive from `public_site_canonical_url`. Do not invent addresses, profiles, or contact details merely to fill structured-data fields.

**Optional direct (non-CDN) fallback frontend** — opt-in via
`nginx_xhttp.fallback_enabled` (off by default). When on, the role renders a
SECOND `server {}` block in the same `vpn-xhttp.conf` listening on
`nginx_xhttp_fallback_port` (group_vars/all.yml, default 2083) and reverse-
proxying the same XHTTP path to the same `127.0.0.1:{{ nginx_xhttp_port }}`
upstream. Purpose: XHTTP delivery survives a Cloudflare / `cdn-front` outage
without touching the primary listener. This is the RU-baseline DIRECT path
— it is publicly reachable, so it carries NO Cloudflare directives
(`set_real_ip_from`, `CF-Connecting-IP`, `real_ip_header`, Origin CA) and
serves the same public site and ordinary 404 page as the primary block.
It is explicitly NOT the `cdn-front` CF path; do not mix the two on one
vhost. The fallback reuses the primary `server_name` cert by default; set
`nginx_xhttp.fallback_server_name` + `fallback_cert_pem` + `fallback_key_pem`
to serve it on a distinct domain. A pre-flight assert in `tasks/main.yml`
rejects a fallback-port collision with REALITY (`xray_port`),
`xray_fallback_port`, `nginx_xhttp_public_port`, or `cdn_front.port`. The
`firewall` role opens the port as a plain direct TCP accept gated by the same
flag (no CF origin-firewall set). Pitfalls below apply unchanged to this
block: HTTP/2 must be enabled on each TLS listener, the port must stay off 443 when REALITY owns
443, and `return 444` is forbidden.

**No `add_header` in child locations** — nginx suppresses inherited headers
when a child block declares any `add_header`. Keep the complete HSTS/CSP/
Permissions/Referrer/nosniff set at server scope in both public vhosts.

**Server-side timing isolation** — XHTTP location has a separate
`proxy_read_timeout` and `proxy_send_timeout`; the public root vhost uses
defaults. Don't mix these — XHTTP needs long-lived streams.

## What's done well

- **SOPS-delivered public certificate** — the role writes `nginx_xhttp.cert_pem` and `key_pem` to the nginx TLS directory with restricted key permissions. Certificate issuance and renewal remain operator-owned; `check-certs.sh` verifies SAN, expiry, and key match before deploy.
- **Validate before activation** — the role enables the rendered site, runs `nginx -t`, then flushes its reload handler immediately so a recovery converge cannot leave nginx serving the previous listener set until the end of a long full-stack play.
- **No public admin path** — there is no admin/status/management endpoint on
  this vhost. The only non-XHTTP public path is the opt-in, secret-token Snell
  evaluation fixture location; it disables access logging and compression and
  remains rate-limited.
- **Coherent HTTP identity** — canonical pages, discovery files, favicon, and error behavior are repository-owned and versioned; TCP/80 is part of the same Terraform-to-Ansible listener contract as HTTPS.
- **Profile-aware port choice** — REALITY-disabled cohorts can set
  `nginx_xhttp_public_port: 443`. Full-stack hosts must keep it off 443
  (Xray's REALITY inbound owns 443).

## Pitfalls

- **Use `listen … ssl http2` while Ubuntu 24.04 ships nginx 1.24** — the standalone `http2 on;` directive only exists in nginx 1.25.1+, so it breaks the supported distro package. The listener form remains valid on newer nginx (with a deprecation warning) and preserves ALPN h2 across the supported fleet.
  The value of HTTP/2 here is an authentic web-server TLS fingerprint (real
  nginx stack, not Go uTLS). It is NOT the June-2026 Condition-3
  multiplexing-protection pattern, which applies only to Russian-cloud-AS
  servers; the foreign-VPS baseline uses a different enforcement path (TCP
  port-range) and that pattern is irrelevant here.
- **Stream module is dynamic on Ubuntu distro nginx** — we use nginx.org
  official repo to get a build with stream as static. If you ever swap to the
  distro package, `libnginx-mod-stream` must be installed and the module
  loaded; the role currently assumes static.
- **SNI ALPN ordering matters for camouflage** — keep `ssl_protocols TLSv1.3`
  + `ssl_ecdh_curve X25519`; weakening these makes the profile fingerprintable.
- **Don't add a `return 444`** — silent close after handshake is rated 9/10
  suspicious by RU active-probing assessments. Return an ordinary branded
  404 for this one site identity; never reuse its exact assets and 404 body
  across unrelated domains because content hashes make a fleet clusterable.
- **The CDN-front role is not a default** — if you find yourself touching
  `cdn-front`, re-read the ADR; the RU baseline is direct.
