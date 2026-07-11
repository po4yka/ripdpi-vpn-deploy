# role: honeypot — active-probing detection

## Design decisions

**Same-host honeypot for cheap signal** — binds plausible-looking listeners
(SSH on 2222, "admin panel" on 9000, "metrics" on 9100) that record hits
without responding. Any hit is a probing signal because legitimate users
have no reason to touch them.

**Logs only; no auto-block** — feeds `monitoring`'s probing summary.
Auto-blocking probers is bait — they rotate IPs faster than we can ban.

**Metrics use a shared writer group** — the textfile directory is root-owned,
setgid and sticky for `node_exporter_textfile`; the honeypot service receives
group write access while monitoring can manage the directory without revoking
it or letting one producer replace another producer's metrics.

**Connection logs are actively size-bounded** — a dedicated systemd timer checks the honeypot logrotate policy every five minutes. The listener reopens `connections.log` for every event, so rename + `create 0640 honeypot honeypot` is safe and avoids `copytruncate` data-loss races.

**Rolling metrics use calendar windows** — every textfile flush evicts minute buckets outside `[now-59, now]`, including after a completely idle period. The current-minute gauge is zero unless the newest bucket belongs to the current wall-clock minute.

**Listener families follow rendered inventory** — IPv4 always binds to `honeypot.listen_addr`; when inventory contains `server_ipv6`, startup also binds `[::]` with `IPV6_V6ONLY=1`. Both sockets are created before either accept loop starts, so a missing promised family fails the service rather than degrading silently.

## What's done well

- **Banner-free** — every honeypot port closes silently after TCP accept.
  No fingerprintable response.
- **Rotated log files** — same retention as `monitoring`.

## Pitfalls

- **Don't expose a honeypot port that legit ops uses** — e.g., if you SSH on
  2222 yourself, do not honeypot 2222. The firewall role validates against
  the effective SSH port.
- **Honeypot ports must be in the firewall allow-list** — otherwise nftables
  drops before the honeypot sees the hit, and you record nothing.
- **Verify each enabled address family separately** — a matching TCP port on IPv4 does not prove the provider's IPv6 firewall opening has a consumer. Keep Molecule and `security-verify.yml` assertions split across `ss -4` and `ss -6`.
- **Rate-limit log writes** — a broad scan can fill the disk otherwise. Keep the in-process event cap, the 10M logrotate threshold, the five-minute timer, and bounded archive retention together.
- **Canary shares the relay IP — observability, not guaranteed early warning** — because the honeypot listeners and the REALITY/VLESS port live on the same IP, a probe that targets the honeypot port and a probe that targets the VPN port are identical from a routing perspective. Under netflow-seeded or infrastructure-enumeration targeting, the adversary may probe both ports simultaneously or probe the VPN port directly without ever hitting the canary. The canary therefore provides a useful probing signal when it fires, but the absence of a canary hit does NOT mean the VPN port was not probed. A separate-IP canary (different VPS, same operator) is the path to real early-warning with meaningful lead time.
