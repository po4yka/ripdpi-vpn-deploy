# probe-ratelimit — what it can and cannot enforce

> **Name caveat.** This role is *not* an active-probing rate-limiter, despite
> the historical framing. REALITY active-probing is invisible to it by
> design. It is a **routing-blackhole abuse rate-limiter**. Read this before
> tuning thresholds or citing it as probe defence.

## The signal the daemon was built to catch — and why it can't

The original intent was: tail `/var/log/xray/access.log`, match lines that
look like a rejected/graylisted handshake, and ban the source IP, throttling
TSPU active-probing of the REALITY listener.

That cannot work, for three independent reasons, all verified against the
pinned Xray-core **v26.3.27**:

1. **Probes never reach the access log.** When a ClientHello fails REALITY
   authentication, Xray-core does not reject the connection — it transparently
   proxies it to the camouflage `target` ("steal-oneself"). The only trace is
   an *error*-log line:

   ```
   [Info] transport/internet/reality: REALITY: processed invalid connection
   ```

   constructed in `transport/internet/reality/reality.go`
   (`errors.New("REALITY: processed invalid connection").AtWarning()`, and the
   TCP-transport wrapper emits the per-IP `... from <ip>:<port>: failed to
   read client hello` variant at `[Info]`). This goes to the **error log**,
   not the `access.log` the daemon tails.

2. **At the pinned loglevel it is suppressed.** `config.json.j2` sets
   `loglevel: "warning"`. `[Info]` general-log messages are filtered out
   (`app/log/log.go`: `*log.GeneralMessage` is logged only when
   `msg.Severity <= g.config.ErrorLogLevel`). So in production the probe line
   is not written at all.

3. **The token never existed.** The old regex `(REJECT|rejected|graylist)`
   matched nothing Xray emits for this path — "graylist" is not an Xray
   concept, and REALITY failures produce no `rejected` access status.

### Why we don't just raise the loglevel

Capturing probe IPs would require (a) tailing `error.log` instead of
`access.log` and (b) raising the error log to `info` or `debug`. Under this
repo's RU/TSPU threat model that is unacceptable: `info`/`debug` dumps every
client's connection metadata — destination IPs, sniffed SNIs, routing
decisions — into a persistent on-disk corpus. The `monitoring` role
deliberately keeps "no long-term log corpus to subpoena"; bumping the
loglevel to feed this daemon would directly undo that. There is no
per-message-type log routing in Xray-core, so the probe line cannot be
isolated from the metadata. **External probing is therefore mitigated
elsewhere** — the firewall (early drop), the `honeypot` role (decoy
detection), and the non-443 fallback inbound — not here.

## What it actually enforces (and this part works)

Access-log messages bypass severity filtering entirely
(`app/log/log.go`: `*log.AccessMessage` is handed to the access logger
unconditionally), so the following are visible at `loglevel: "warning"`:

- **Blackholed traffic** — the routing rules in `config.json.j2` send
  BitTorrent, UDP/443 (QUIC), and RFC1918 destinations to the `block`
  outbound. Xray logs these as `accepted` with the outbound tag in the
  detour bracket:

  ```
  from tcp:203.0.113.55:51999 accepted udp:142.250.1.1:443 [vless-reality -> block] email: <client>
  ```

  The detour separator varies (`->`, `>>`, `==>` per
  `app/dispatcher/default.go`); `BLOCK_RE` matches the `block` tag regardless.

- **VLESS-layer rejections** — a malformed request after a *successful*
  REALITY handshake yields a `rejected` access status
  (`common/log/access.go` `AccessRejected = "rejected"`).

A source IP that trips these `rejects_per_window` times inside
`window_seconds` is added to the `probe_offenders` nftables set for
`ban_seconds`. The source IP on these lines is the **client's real IP**, so
the carrier-NAT caveat in `CLAUDE.md` applies: a strict threshold can ban a
whole NAT pool.

## Observability: the dead-contract gauge

Because the failure mode of a log-token control is *silent* (counters sit at
zero and look like "no abuse"), the daemon exports:

| Metric | Meaning |
|---|---|
| `vpn_probe_ratelimit_lines_total` | access-log lines tailed |
| `vpn_probe_ratelimit_events_total` | block/rejected events matched |
| `vpn_probe_ratelimit_bans_total` | IPs banned |
| `vpn_probe_ratelimit_dead_contract` | `1` once `lines_total ≥ dead_contract_min_lines` while `events_total == 0` |

`dead_contract == 1` means **investigate**: either the access-log format
drifted under an Xray bump (token/sink contract broken) or this cohort
genuinely never trips a blackhole route. Either way it is no longer
indistinguishable from "quiet". Alert on it operator-side.

## Regression guard

`tests/unit/test_probe_ratelimit.py` renders this template and feeds it the
golden fixtures `tests/fixtures/xray-access-sample.log` (benign + blackholed +
rejected) and `tests/fixtures/xray-error-sample.log` (the real REALITY probe
line). It asserts the daemon bans exactly the blackholed/rejected offenders,
never the benign clients, never RFC1918 sources, and — critically — never the
error-log probe line, encoding the design limitation above as a test.
