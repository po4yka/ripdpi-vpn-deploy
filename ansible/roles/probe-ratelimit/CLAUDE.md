# role: probe-ratelimit — routing-blackhole abuse rate-limiter

## Design decisions

**Bans blackhole/rejected abuse, NOT external probes** — the historical
name implied it throttles REALITY active-probing. It cannot: REALITY
forwards failed-auth probes to the camouflage `target` and logs
`REALITY: processed invalid connection` to *error.log* at `[Info]`
(suppressed at `loglevel: "warning"`), never to the access.log this daemon
tails. See `README.md`. What it actually enforces: authenticated clients
whose traffic is routed to the `block` outbound (BitTorrent / QUIC-443 /
RFC1918) or `rejected` at the VLESS layer — both access-log-visible
regardless of loglevel (access messages bypass severity filtering).

**Network-layer drop, not Xray policy** — Xray exposes no runtime graylist
API, so offenders go into the nftables `probe_offenders` set (firewall role
owns it) for an early drop.

**Threshold is conservative** — defaults 5 events / 60s / IP. The source IP
on a blackhole line is the *client's* real IP, so a strict limit on a
carrier-NAT pool takes out legitimate clients first.

## What's done well

- **Decision core is a pure `RateLimiter` class** — no I/O, unit-tested
  against golden fixtures (`tests/unit/test_probe_ratelimit.py`).
- **Separator-agnostic block match** — `BLOCK_RE` matches `[... block]`
  across the `->`/`>>`/`==>` detour forms (app/dispatcher/default.go).
- **Dead-contract gauge** — `vpn_probe_ratelimit_dead_contract` flips to 1
  after N lines with zero matched events, so a regressed sink/token is
  observable instead of looking like a quiet cohort.
- **Ephemeral state** — per-IP counters are in-memory; restart wipes.

## Pitfalls

- **It does not see probers — do not market it as probe defence.** External
  active-probing is mitigated by firewall + honeypot + non-443 fallback.
- **CDN-fronted paths break source attribution** — behind a CDN the source
  IP is the edge IP. Disable this role when `cdn-front` is on.
- **Don't tune below the carrier-NAT threshold** — banning a NAT IP bans
  every user behind it, including their working tunnel.
- **Token/sink are pinned to Xray-core v26.3.27 access-log format** — re-run
  `tests/unit/test_probe_ratelimit.py` after any Xray pin bump; if the
  access-log line shape changed, the dead-contract gauge will also rise on
  live nodes.
