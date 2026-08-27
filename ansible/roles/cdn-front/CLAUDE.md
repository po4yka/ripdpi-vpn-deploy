# role: cdn-front — Cloudflare XHTTP fallback (TACTICAL ONLY)

## Design decisions

**Off by default** — `vpn.enable_cdn_front: false`. Rationale lives in
`docs/CDN-DECISION.md`: as of 2026-04, RU traffic to Cloudflare egresses via
RU PoPs (DME/KJA/LED) which carry TSPU, with a 16KB byte-threshold curtain
applied to non-`/cdn-cgi/trace` traffic.

**Independent of `nginx-xhttp`** — when `cdn-front` is on, the public 443
listener gains Cloudflare real-IP restoration (`set_real_ip_from` for CF
ranges, `CF-Connecting-IP`), Origin CA cert, and Authenticated Origin Pulls.
`nginx-xhttp` keeps doing its direct thing on its own port.

**Cold start is explicit** — a stopped nginx is seeded with `--seed-only`,
then the CDN vhost is installed and validated before the service starts.
The packaged default site is disabled. Active refreshes and timer runs
must reload successfully; they retain transactional rollback on failure.

## What's done well

- **Origin CA is generated locally, not pulled from CF** — avoids a
  trust-on-first-use moment.
- **`real_ip_recursive on`** — proper handling of multi-proxy chains.
- **Prefix refresh is transactional** — every CIDR is parsed with the expected address family, nginx candidates are syntax-checked, and both nftables sets are replaced in one checked batch before caches are published.

## Pitfalls

- **Do not enable this for the RU baseline** — re-read the ADR. Use it only
  when the failure shape is "TLS handshake never completes from this network,
  completes from elsewhere" and a non-RU CDN PoP is reachable.
- **CF ranges drift** — keep `cloudflare_ranges.txt` fresh via the
  `update-cf-ranges.sh` script (run from operator workstation, not server).
- **`Authenticated Origin Pulls` is mandatory** — without it, anyone with the
  origin IP can bypass the CDN. The role refuses to start if the AOP cert is
  missing.
- **Mixing CF and direct on the same vhost is forbidden** — separate
  `server_name`/`listen` blocks. Header inheritance otherwise leaks origin IP.
- **`nginx -t` needs writable PID/log files even for validation** — the
  refresh sandbox grants only `/run/nginx.pid` and `/var/log/nginx` beyond
  prefix state, and starts after nginx so the PID bind mount exists. Test
  `systemctl start cdn-front-prefix-refresh.service`, not only the script.
