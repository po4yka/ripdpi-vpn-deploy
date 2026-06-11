# role: nginx-xhttp — P1 HTTPS path

## Design decisions

**Direct only by default** — `vpn.enable_cdn_front` is false in baseline.
The role ships nginx pointed at a public CA cert for the operator's domain,
listening on `nginx_xhttp_public_port` (default 8443), reverse-proxying the
XHTTP path to Xray on `127.0.0.1:10085`. No `set_real_ip_from`, no
`CF-Connecting-IP`, no Origin CA. Rationale: `docs/CDN-DECISION.md`.

**No `add_header` in child locations** — nginx suppresses parent headers when
any child block has `add_header`. We declare HSTS/CSP/etc. via a `map`
directive at the http{} level.

**Server-side timing isolation** — XHTTP location has a separate
`proxy_read_timeout` and `proxy_send_timeout`; the public root vhost uses
defaults. Don't mix these — XHTTP needs long-lived streams.

## What's done well

- **Self-contained on-disk cert** — `acme_sh` issues from Let's Encrypt with
  HTTP-01; the role re-renews idempotently. `check-certs.sh` verifies SAN +
  expiry + modulus match.
- **No public admin path** — there is no admin/status/management endpoint on
  this vhost. The only public path is the XHTTP location.
- **Profile-aware port choice** — REALITY-disabled cohorts can set
  `nginx_xhttp_public_port: 443`. Full-stack hosts must keep it off 443
  (Xray's REALITY inbound owns 443).

## Pitfalls

- **`http2 on;` is required, not implied** — nginx 1.25+ split it from
  `listen … http2`. Without it ALPN downgrades to HTTP/1.1, a fingerprint.
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
  suspicious by RU active-probing assessments. Use 403/404 with nginx's
  default body (custom bodies are content-hashable).
- **The CDN-front role is not a default** — if you find yourself touching
  `cdn-front`, re-read the ADR; the RU baseline is direct.
