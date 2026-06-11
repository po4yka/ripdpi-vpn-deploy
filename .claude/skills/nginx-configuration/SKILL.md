---
name: nginx-configuration
description: Nginx config for the vpn-deploy P1 profile (nginx + XHTTP direct) and the subscription-host role. Reverse proxy, HTTP/2, TSPU-aware TLS hardening. Use when editing ansible/roles/nginx-xhttp/** or ansible/roles/subscription-host/**. vpn-deploy project variant.
---

# Nginx Configuration (vpn-deploy)

Nginx is used in two roles here:

1. **`nginx-xhttp`** — P1 profile front. Terminates TLS, exposes the XHTTP path for Xray,
   and returns a cover page for everything else.
2. **`subscription-host`** — serves device-specific recipient pages (`vpnd/templates/recipient.html`)
   over HTTPS with a unique path per device.

Both run on Debian/Ubuntu under systemd. There is no Docker-nginx, no upstream pool, no
load balancing. Discard upstream examples that reference those.

## Threat model

- TSPU-class adversary observes TLS metadata. Use HTTP/2 + modern ciphers but no exotic
  fingerprint that lights up a flow classifier.
- ALPN must include `h2` and `http/1.1`.
- Cover page must be plausible for the SNI used — `example.com` is not plausible.
- Rate limiting is enforced at **nftables** via the `policy-ratelimit` role, not in nginx.
  Do not add `limit_req_zone` blocks — they conflict with the firewall layer.

## Hard rules

- **No public admin panel.** No `/status`, no `stub_status`, no `nginx_status` exposed on
  public listeners. Stub status, if enabled, must bind to `127.0.0.1` only.
- **No CDN as the RU baseline.** P1 is direct. See `docs/CDN-DECISION.md`.
- **No `server_tokens on`.** Suppress nginx version in headers and error pages.
- **TLS keys are SOPS-encrypted** in `secrets/`, decrypted into a tmpfs path at deploy
  time. Never committed.
- **Listen on the configured port from `group_vars`**, not hardcoded `443`. The P1 port is
  cohort-configurable.

## Skeleton — nginx-xhttp role

```nginx
# /etc/nginx/sites-available/xhttp.conf  (rendered from role template)

server {
    listen {{ nginx_xhttp_port }} ssl http2;
    listen [::]:{{ nginx_xhttp_port }} ssl http2;
    server_name {{ nginx_xhttp_server_name }};

    ssl_certificate     /run/nginx-keys/fullchain.pem;
    ssl_certificate_key /run/nginx-keys/privkey.pem;
    ssl_protocols       TLSv1.3 TLSv1.2;
    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-CHACHA20-POLY1305;
    ssl_prefer_server_ciphers off;

    # XHTTP path for Xray
    location {{ xray_xhttp_path }} {
        grpc_pass grpc://127.0.0.1:{{ xray_xhttp_local_port }};
        grpc_read_timeout 3600s;
        grpc_send_timeout 3600s;
        client_max_body_size 0;
    }

    # Cover page for anything else
    location / {
        root /var/www/cover;
        index index.html;
        try_files $uri $uri/ =404;
    }
}
```

## Skeleton — subscription-host role

- One unique location per device, path derived from a per-device SOPS-stored token.
- `add_header Cache-Control "no-store"`.
- No directory listing, no `autoindex`.
- HSTS optional but recommended once cohort has stable hostname.

## Don'ts

- No `gzip on` for already-compressed application/octet-stream paths (recipient JSON is
  small; gzip leaks size class).
- No `access_log` on subscription endpoints — log retention is a leak surface.
  Error log only, with `log_not_found off`.
- No `proxy_pass` to a cloud upstream — there are no cloud backends in P1.
- No `if (...)` in `location` blocks unless absolutely required (nginx anti-pattern).
- No third-party modules. Stick to the Debian/Ubuntu `nginx-extras` package or the role's
  pinned compile.

## Testing

- Molecule scenario for both roles runs `nginx -t` and `systemd-analyze verify` against
  the rendered unit.
- Add a curl-based smoke test to the role's `verify.yml` that hits the XHTTP path and
  asserts a non-zero gRPC response.

## See also

- `ansible/roles/nginx-xhttp/CLAUDE.md` — role-specific decisions
- `ansible/roles/subscription-host/CLAUDE.md` — per-device URL strategy
- `[[security-review]]` — admin panel rule, rate-limit layer
- `[[systemd]]` — nginx unit hardening overrides
