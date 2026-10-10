# role: policy-ratelimit — routing-blackhole abuse rate-limiter

## Design decisions

The root policy unit bounds capabilities to NET_ADMIN, so root UID alone cannot
read a dedicated Xray user's logs. Its sole extra reader grant is membership in
the configured Xray log group; validated 0640 logs admit that reader while
other identities remain denied. No DAC bypass capability is added.
The role ensures the named reader group without changing an existing GID, so
an independently enabled detector can still run and report unavailable input
when Xray is disabled or its log has not appeared.

**Bans blackhole/rejected abuse, NOT external probes** — the historical
`probe-ratelimit` name implied it throttles REALITY active-probing. It
cannot: on failed auth `xtls/reality`'s `func Server` proxies the prober to
the camouflage `Dest` ("steal-oneself") and surfaces only a returned
`fmt.Errorf("REALITY: processed invalid connection from %s …")`, logged by
Xray's inbound worker at `[Info]` to *error.log* (suppressed at
`loglevel: "warning"`), never to the access.log this daemon tails. The ADR in
`README.md` records the full mechanism (pinned Xray v26.3.27 / reality
9234c772ba8f) and why path (b) over an nginx-stream front. What it actually
enforces: authenticated clients whose traffic is routed to the `block`
outbound (BitTorrent / QUIC-443 / RFC1918) or `rejected` at the VLESS layer —
both access-log-visible regardless of loglevel (access messages bypass
severity filtering).

**Network-layer drop, not Xray policy** — Xray exposes no runtime graylist
API, so offenders go into the nftables `policy_offenders` set (firewall role
owns it) for an early drop.

**Threshold is conservative** — defaults 5 events / 60s / IP. The source IP
on a blackhole line is the *client's* real IP, so a strict limit on a
carrier-NAT pool takes out legitimate clients first.

Same-inode truncation resets the existing read offset when file size shrinks;
inode replacement reopens from the beginning. Permanent regressions exercise
both kernel file identities, subsequent input and absence of double counting.
The correct reader is preserved; bytes overwritten between polls are not an
input-recovery guarantee.

## What's done well

- **Decision core is a pure `RateLimiter` class** — no I/O, unit-tested
  against golden fixtures (`tests/unit/test_policy_ratelimit.py`).
- **Separator-agnostic block match** — `BLOCK_RE` matches `[... block]`
  across the `->`/`>>`/`==>` detour forms (app/dispatcher/default.go).
- **Dead-contract gauge** — `vpn_policy_ratelimit_dead_contract` flips to 1
  after N lines with zero matched events, so a regressed sink/token is
  observable instead of looking like a quiet cohort.
- **Ephemeral state** — per-IP counters are in-memory; restart wipes.

## Pitfalls

- **It does not see probers — do not market it as probe defence.** External
  active-probing is mitigated by firewall + honeypot + non-443 fallback.
- **Single-layer contract: this role does not do HTTP route limiting** —
  browser-facing vhosts (snell-evaluation, subscription endpoints) throttle
  at nginx `limit_req` by design; nftables cannot express per-route/burst
  granularity. Do not add duplicate nginx limits behind these chains or
  nft chains in front of those vhosts — one layer per surface.
- **CDN-fronted paths break source attribution** — behind a CDN the source
  IP is the edge IP. Disable this role when `cdn-front` is on.
- **Don't tune below the carrier-NAT threshold** — banning a NAT IP bans
  every user behind it, including their working tunnel.
- **Token/sink are pinned to Xray-core v26.3.27 access-log format** — re-run
  `tests/unit/test_policy_ratelimit.py` after any Xray pin bump; if the
  access-log line shape changed, the dead-contract gauge will also rise on
  live nodes.

- Idle input still publishes a heartbeat; unavailable input has a separate gauge.
  Source windows expire and have a fixed capacity with an overflow counter.
- Textfile publication uses directory descriptors and random exclusive temporary
  files; reject symlink outputs and preserve prior bytes when publication fails.

- Ordinary site convergence always invokes lifecycle reconciliation. The
  `policy_ratelimit_role_enabled` input selects enable or owned runtime retirement before
  secret/package guards. Disable stops units and removes only declared authority;
  shared packages, immutable runtime receipts, historical logs and recovery data
  remain available for a later explicit recovery.
