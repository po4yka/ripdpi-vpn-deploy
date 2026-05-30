# Per-ASN payload-size throttling probe

`scripts/probe-payload-throttle.sh` measures whether a transit path
applies a silent throughput/latency penalty once a single response body
crosses a size threshold near **~16 KiB**. Small requests clear cleanly;
larger ones stall, time out, or have their RTT inflated. The probe walks
an escalating ladder of payload sizes against an operator-supplied
endpoint and classifies the path by its **observed signature**.

Like `scripts/test-tls-policing.sh`, this is a **client-side** probe: run
it from a filtered client path you care about, **not** from the VPS. A
common pattern is to ssh into a low-cost box inside the cohort's path and
point the probe at an operator-controlled echo/download endpoint that
serves a body of the requested byte count (`?bytes=<N>`).

## Technical-signature framing — no brand names

Verdicts are keyed to the target **ASN** (`AS<number>`) plus the observed
behavioural signature (size threshold, RTT spike, completion cliff) — the
same project-wide rule that governs the probe-matrix destination classes
(see `PROBE-MATRIX.md`, "Destination classes"). The `ORG` and `COUNTRY`
columns returned by `scripts/probe-asn.sh` MUST NOT appear in any slug,
filename, state path, comment, or verdict field. Class the path by ASN
behaviour, never by operator or geography (root `CLAUDE.md` hard rule).

ASN resolution reuses `scripts/probe-asn.sh` (Team Cymru whois) — the same
primitive `asn-drift.sh` uses. Field 2 is the ASN, field 3 the prefix.

## Verdict schema (reused)

The probe emits exactly one JSON object on stdout matching the canonical
probe verdict shape used by `scripts/probe-matrix-cell.sh` and the
probe-matrix cells (`PROBE-MATRIX.md`, `schema_version: 1`):

```jsonc
{
  "verdict": "ok",            // ok | throttled | blocked | unknown | error
  "rtt_ms": 42,               // median of completed steps, or null
  "asn": "AS64500",           // technical key — never a brand name
  "prefix": "203.0.113.0/24", // from probe-asn.sh, optional
  "threshold_bytes": 16384,   // set when verdict == throttled
  "sizes": [                  // per-step breakdown
    {"bytes": 1024,  "completed": true,  "rtt_ms": 30},
    {"bytes": 16384, "completed": false, "rtt_ms": null}
  ],
  "error_kind": "asn lookup failed"  // populated only when verdict == error
}
```

All diagnostic noise goes to stderr; a non-zero exit is read by
orchestrators as `error`. `unknown` (never `ok`) is emitted for
indeterminate results so an unexpected-OK alert is not silently swallowed.

### Classification logic

- **`ok`** — every payload size completes and no `>=16 KiB` step shows an
  RTT spike relative to the small-payload baseline.
- **`throttled`** — the small-payload baseline mostly completes, but a
  `>=16 KiB` step shows a **completion cliff** (the step fails) or a
  **P50 RTT spike** (`>= SPIKE_FACTOR ×` baseline P50). `threshold_bytes`
  records the first offending size.
- **`blocked`** — no payload size completes at all (the path drops the
  connection outright rather than selectively throttling by size).
- **`unknown`** — indeterminate (e.g. even the small payloads fail, so the
  signal is connectivity, not size throttling; or no baseline samples).
- **`error`** — a tool is missing or the ASN lookup failed; `error_kind`
  carries the reason.

## State

When state persistence is enabled (default), the latest verdict is written
atomically (tmp + `mv`, `chmod 0600`) to:

```
${XDG_STATE_HOME:-$HOME/.local/state}/vpn-deploy/payload-throttle/AS<num>.json
```

State is keyed by `AS<num>` only — never by host/IP — so a path's history
survives endpoint rotation. Pass `--no-state` to skip the write.

## Running it

```sh
make probe-payload-throttle HOST=endpoint.example.com
make probe-payload-throttle HOST=1.2.3.4 PORT=443 \
    SIZES=1024,4096,8192,16384,24576,32768
make probe-payload-throttle HOST=endpoint ASN=AS64500   # skip ASN lookup
```

A `@daily` operator cron is wired by `scripts/install-operator-crons.sh`
when `PAYLOAD_THROTTLE_HOST` is exported. A daily cadence is deliberate:
the probe issues real traffic, so a tight poll interval would itself
become a DPI signature (see `PROBE-MATRIX.md` on the 300 s default).

## Cross-references

- `PROBE-MATRIX.md` — the per-(protocol × destination) matrix that shares
  this verdict schema and the technical-signature destination classes.
- `scripts/probe-asn.sh` — the ASN-resolution primitive.
- `scripts/test-tls-policing.sh` — sibling client-side path probe.
