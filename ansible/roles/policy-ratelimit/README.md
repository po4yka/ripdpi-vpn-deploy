# policy-ratelimit — policy-violation rate-limiter (NOT a probe defence)

This role rate-limits **policy-violating traffic from already-authenticated
clients** — connections the Xray routing rules send to the `block` outbound
(BitTorrent, QUIC/UDP-443, RFC1918 destinations) or that the VLESS layer marks
`rejected`. It tails `/var/log/xray/access.log` and adds repeat offenders to
the nftables `policy_offenders` set with a TTL.

It is **not** an active-probing defence, and must not be cited as one. REALITY
is the active-probing defence. The ADR below records why, with the verified
Xray mechanism that forces the decision. Read it before tuning thresholds or
re-scoping the daemon.

## ADR: policy limiter, not probe detector

**Status:** accepted. Supersedes the role's original `probe-ratelimit` framing.

**Context.** The role was first written to throttle TSPU active-probing of the
REALITY listener by tailing `access.log` for a rejected/graylisted handshake.
That contradicts how REALITY actually works — and our own threat model. The
re-architecture forced a choice between two implementations.

**Verified mechanism (the constraint that drives the decision).** Pinned
`Xray-core v26.3.27`, which vendors `github.com/xtls/reality
v0.0.0-20260322125925-9234c772ba8f` (per Xray-core's `go.mod`). On the server
side, when an incoming ClientHello fails REALITY authentication (`func Server`
in `xtls/reality/tls.go`):

- The server does **not** reject. It dials the camouflage target
  (`config.DialContext(ctx, config.Type, config.Dest)`) and proxies the raw
  bytes both ways with `io.Copy` — the "steal-oneself" fallback. The prober
  gets a real TLS session to the donor site, indistinguishable from a genuine
  visitor.
- The only per-IP diagnostic is a **returned** error,
  `fmt.Errorf("REALITY: processed invalid connection from %s: %s", remoteAddr, failureReason)`.
  The verbose `remoteAddr` / `ClientShortId` trace lines are `fmt.Printf`
  guarded by `if config.Show` → stdout, and `show` is off in production.
- That returned error propagates to Xray-core's inbound worker, which logs the
  accept failure at **`[Info]`** to the **error log** — never to the
  `access.log` this daemon tails. (An earlier note citing
  `errors.New("REALITY: processed invalid connection").AtWarning()` was wrong:
  that `.AtWarning()` form is the *client* `UClient` dial path in Xray-core's
  own `transport/internet/reality/reality.go`, not the server.)
- At the pinned `loglevel: "warning"`, that `[Info]` line is suppressed
  entirely (`app/log/log.go` gates `*log.GeneralMessage` on
  `msg.Severity <= g.config.ErrorLogLevel`).
- The steal-oneself copy runs at the **transport layer**, below the dispatcher
  that writes `access.log` records, so the probe produces no usable access-log
  entry at all — the prober's source IP never appears there with an actionable
  token.

So a probe is, by design, invisible to a tailer: the per-IP detail is a
suppressed `[Info]` error-log line (or `show`-gated stdout), and the
connection itself leaves no `access.log` record the daemon could key on. The
old regex `(REJECT|rejected|graylist)` matched nothing Xray emits for this
path — "graylist" is not an Xray concept.

**Option (a) — re-source to the correct probe signal.** Put an nginx `stream{}`
front with `ssl_preread on` ahead of xray on :443 (reads SNI without
terminating TLS) and/or run a `tcpdump` SYN-capture, then score connections
behaviourally (empty SNI, session <2 s, burst frequency, temporal correlation
of a probe 1–3 s after legitimate traffic, TCP-window/MSS/TTL anomalies) and
feed a graylist with hot-reload. This is the upstream reference design.

**Option (b) — stop calling it probe defence.** Keep xray on :443 with REALITY
as the front-line camouflage, rename the role to reflect what it can enforce,
and scope the daemon to the policy violations it can actually see in
`access.log`.

**Decision: (b).** Reasons, in priority order:

1. **(a) demotes REALITY on the RU baseline.** P0 is VLESS+REALITY+Vision
   *direct* on TCP/443. REALITY's steal-oneself fallback *is* the
   active-probing defence — that is exactly why VLESS+REALITY survived the
   Aug-2025 TSPU active-probing wave that broke Trojan and VMess. Inserting an
   `ssl_preread` stream hop ahead of it changes the listener topology of the
   baseline protocol, turning a one-daemon question into an architecture
   change to the thing that already works.
2. **(a)'s signal sources are the exact persistent metadata corpus this repo
   refuses to keep.** An `ssl_preread` stream-access log records every
   connection's SNI + timing; a `tcpdump -w` SYN-capture writes every :443 SYN
   to disk. That is the same "no long-term log corpus to subpoena" line the
   `monitoring` role holds — and the same reason we will not raise xray's
   loglevel to see probes (see mechanism above). Path (a) would build the
   corpus we deliberately declined to build.
3. **(a) is a large new attack surface for a default-off, TACTICAL role** — a
   stateful packet scorer plus a graylist reload path, re-implementing a
   defence REALITY already provides architecturally.

**Consequence.** Active-probing mitigation stays where it belongs: REALITY
itself (camouflage), the firewall scanner-ASN denylist (early drop of known
probe ranges), the `honeypot` role (decoy), and the non-443 fallback inbounds.
This daemon owns exactly one job — rate-limiting policy-violating egress from
authenticated clients — and the rest of this document is scoped to that.

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
`window_seconds` is added to the `policy_offenders` nftables set for
`ban_seconds`. The source IP on these lines is the **client's real IP**, so
the carrier-NAT caveat in `CLAUDE.md` applies: a strict threshold can ban a
whole NAT pool.

## Observability: the dead-contract gauge

Because the failure mode of a log-token control is *silent* (counters sit at
zero and look like "no abuse"), the daemon exports:

| Metric | Meaning |
|---|---|
| `vpn_policy_ratelimit_lines_total` | access-log lines tailed |
| `vpn_policy_ratelimit_events_total` | block/rejected events matched |
| `vpn_policy_ratelimit_bans_total` | IPs banned |
| `vpn_policy_ratelimit_dead_contract` | `1` once `lines_total ≥ dead_contract_min_lines` while `events_total == 0` |

`dead_contract == 1` means **investigate**: either the access-log format
drifted under an Xray bump (token/sink contract broken) or this cohort
genuinely never trips a blackhole route. Either way it is no longer
indistinguishable from "quiet". Alert on it operator-side.

## Regression guard

`tests/unit/test_policy_ratelimit.py` renders this template and feeds it the
golden fixtures `tests/fixtures/xray-access-sample.log` (benign + blackholed +
rejected) and `tests/fixtures/xray-error-sample.log` (the real REALITY probe
line). It asserts the daemon bans exactly the blackholed/rejected offenders,
never the benign clients, never RFC1918 sources, and — critically — never the
error-log probe line, encoding the design limitation above as a test.
