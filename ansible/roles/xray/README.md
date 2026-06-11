# xray role — operator notes

## REALITY target and serverNames validation

`xray.target` and `xray.server_names` are passed verbatim into the REALITY
inbound config. The role asserts at pre-flight that both values are non-empty,
but correctness of the chosen target is the operator's responsibility:

- Run `scripts/validate-reality-target.sh <target>` to check TLS
  fingerprint compatibility, cert chain, and H2/H3 support before adopting a
  new target.
- Run `scripts/probe-sni-survival.sh <target>` from a filtered vantage point
  (a node inside the target network, or a probe machine on the relevant
  access path) to verify the SNI passes the censor's filters.

Choosing a target that is itself blocked or that leaks a distinctive
fingerprint negates the REALITY camouflage. The pre-flight assert catches
empty values but cannot substitute for operational verification.

## QUIC / HTTP-3 outbound blocking (`xray_block_quic_outbound`)

The routing config in `templates/config.json.j2` carries an anti-fingerprint
rule that sends all outbound **UDP/443 (QUIC)** to the `block` blackhole
outbound. This is **on by default** and controlled by a single role variable:

```yaml
# ansible/roles/xray/defaults/main.yml (or override in group_vars / a cohort)
xray_block_quic_outbound: true   # default: block QUIC egress
```

### Why it is on by default

When a proxied client speaks QUIC, the exit node emits UDP/443 to arbitrary
destinations. A censor watching the VPS can use that UDP/443 flow as a
**leak fingerprint** that distinguishes a proxy/exit from an ordinary
TLS-over-TCP host. Blackholing outbound QUIC keeps the exit's egress shape
uniformly TCP, removing that signal. This matches the threat model in the repo
hard rules (RU-internet / TSPU-aware) and is the safe baseline.

### The trade-off (why you might turn it off)

Blocking outbound QUIC **disables HTTP/3 for every client routed through the
proxy.** The effect is a graceful degradation, not a breakage:

- Browsers and modern apps that try HTTP/3 get no UDP/443 response and
  **transparently fall back to HTTP/2 over TCP** (RFC 9114 clients always keep
  a TCP path). Pages still load.
- The cost is **performance**, not function: on lossy or high-latency links
  HTTP/3's loss recovery and 0-RTT resumption are faster than HTTP/2-over-TCP,
  so heavy users (video, large downloads, mobile networks) may see slower
  transfers and more head-of-line blocking.
- A few QUIC-only paths exist in practice (some Google services prefer QUIC,
  WebRTC data is separate and unaffected here since this rule is scoped to
  UDP/443). These still work over their TCP fallbacks.

### When to disable it

Set `xray_block_quic_outbound: false` for a deploy or cohort where **HTTP/3
performance matters more than the egress fingerprint surface** — for example a
node serving a cohort on a high-loss mobile network, on a provider/IP that is
not under active QUIC-aware scrutiny. Leave it **on** for the RU baseline.

```yaml
# e.g. ansible/group_vars/<cohort>.yml
xray_block_quic_outbound: false
```

Render behaviour is covered by `tests/unit/test_xray_quic_toggle.py`: the
UDP/443 → `block` rule is present in the rendered `config.json` when the toggle
is on and absent when off, and the config stays valid JSON either way.
