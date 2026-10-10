# role: nginx-xhttp — P1 HTTPS path

## Design decisions

Publication change reporting compares recaptured authority under the writer
lock. The preliminary snapshot validates recoverability; check mode computes
its own predicted difference without runtime publication.

**Direct only by default** — `vpn.enable_cdn_front` is false in baseline.
The role ships nginx pointed at a public CA cert for the operator's domain,
listening on `nginx_xhttp_public_port` (default 8443), reverse-proxying the
XHTTP path to Xray on `127.0.0.1:10085`. No `set_real_ip_from`, no
`CF-Connecting-IP`, no Origin CA. Rationale: `docs/CDN-DECISION.md`.

**The primary hostname resolves locally without external DNS** — the role
owns a marked `/etc/hosts` entry from `nginx_xhttp.server_name` to the
provider-assigned `vpn_service_address` and verifies it through NSS. Public
DNS remains an independent client-path requirement; this entry only makes
same-node operations deterministic.

**Ordinary paths are a real static site** — the role publishes repository-owned content to `/var/www/public-site`, serves it on the primary and alternate HTTPS vhosts, and redirects TCP/80 to the configured HTTPS port. Identity pages are rendered from `templates/public-site/` so canonical metadata follows `public_site_canonical_url`; reusable CSS, favicon, search logo, and the host-neutral 404 remain static files. The secret XHTTP path remains a separate exact transport seam. Keep admin, metrics, status, and health endpoints off the public vhost.

**One search identity graph** — `LLM Model Notes` is the sole public name. The home page emits `WebSite` + `Organization`; supporting pages emit `WebPage`; articles emit `Article` with the same visible author/publisher and dated metadata. Stable entity IDs, logo URLs, canonicals, Open Graph URLs, and the lowercase domain fallback all derive from `public_site_canonical_url`. Do not invent addresses, profiles, or contact details merely to fill structured-data fields.

**Maintenance signals come from real content** — the home page's visible update date, the project log, article metadata, and `feed.xml` must describe the same material publications. Every HTML page advertises the Atom feed; feed and entry URLs derive from `public_site_canonical_url`, and both HTTPS vhosts serve it as `application/atom+xml`. Advance dates only for substantive content changes; do not manufacture activity with fake contacts, counters, status endpoints, or empty log entries.

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

**Both XHTTP locations suppress access logging** — primary and fallback transport paths keep request/session identifiers out of public-site logs; ordinary site requests retain their access logs.

The shared publisher journals complete prior/desired rows, exact boot/running
state and a versioned phase before each live boundary. Recognized interruption
recovers only that write set under the unit lock, restores prior service state,
and then re-converges normally. Foreign bytes and unknown journals fail closed.
Private per-owner receipts bind stable managed authority; a missing/stale receipt
forces adoption even when disk bytes are unchanged. Runtime validation precedes
the fsynced receipt. Reload also requires a fresh stable live worker pool under
the same trusted master/executable identity; command acknowledgement and disk
validation alone cannot acknowledge adoption. Failed/missing new workers retain
intent and compensate. SIGKILL proofs cover publication, activation and recovery.
An absent validation root containing only absent desired rows remains absent in
the candidate. This lets a never-enabled owner reconcile against an active shared
nginx on later convergences without creating a payload tree or skipping adoption.
Missing roots required by a desired file or credential binding still refuse.
An unchanged all-absent owner may record only a disk-absence witness while the
unit is actually inactive with MainPID zero. Its private receipt binds the
kernel boot UUID and CLOCK_BOOTTIME in the same clock ticks as `/proc/PID/stat`.
A later master that started strictly after that witness on the same boot can
acknowledge the absence without a redundant reload, after stable canonical
master/worker identity and candidate plus actual-namespace validation. Promotion
rechecks that generation around its durable receipt write. Equal/older starts,
another boot or stale fingerprints require real adoption; future ticks and
malformed/foreign private authority refuse. This preserves first-to-second
shared-role idempotence without claiming an inactive unit adopted configuration.

## What's done well

- **SOPS-delivered public certificate** — the role writes `nginx_xhttp.cert_pem` and `key_pem` to the nginx TLS directory with restricted key permissions. Certificate issuance and renewal remain operator-owned; `check-certs.sh` verifies SAN, expiry, and key match before deploy.
- **Complete candidate before publication** — `tasks/transaction.yml` accepts an exact owned write set, roots, validator argv and target unit. It stages full roots, validates at actual absolute paths in a private mount namespace, then publishes under a per-unit lock. Ordinary activation failure restores prior bytes, runtime and exact boot enablement; failed compensation retains a private pending snapshot and refuses reuse. Ordinary candidate-preparation failure removes only this invocation’s pending snapshot while preserving live bytes, so correcting an unrelated FIFO permits a valid retry. Once publication or activation may occur, failed compensation retains recovery authority. Credential roots are bound to the exact unit credential paths only inside validation namespace. Check mode predicts changes without creating state or activating runtime.
- **Fresh-host check mode plans nginx without activating it** — the role checks for the distro unit and requires a planned package installation when it is absent. Reload and start remain runtime actions on a real converge; check mode does not claim a nonexistent service is active.
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
- **SNI ALPN ordering matters for camouflage** — keep `ssl_protocols TLSv1.3`
  + `ssl_ecdh_curve X25519`; weakening these makes the profile fingerprintable.
- **Don't add a `return 444`** — silent close after handshake is rated 9/10
  suspicious by RU active-probing assessments. Return an ordinary branded
  404 for this one site identity; never reuse its exact assets and 404 body
  across unrelated domains because content hashes make a fleet clusterable.
  The canonical decoy scaffold for new surfaces is two trees under this role:
  `templates/public-site/` holds the Jinja pages (which reference
  `/assets/site.css`, `/favicon.svg`, and `/logo.svg`), and
  `files/public-site/` holds the served static assets plus `404.html`. Copy
  and re-theme BOTH per identity; copying only the templates produces a decoy
  with missing assets and 404.
- **The CDN-front role is not a default** — if you find yourself touching
  `cdn-front`, re-read the ADR; the RU baseline is direct.
- **Do not pin the hostname to loopback** — use `vpn_service_address` so
  same-node resolution exercises the same public listener identity as a
  client. Re-render inventory and redeploy when the provider address changes.
