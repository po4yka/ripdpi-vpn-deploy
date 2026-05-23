# Multi-protocol simultaneity DPI probe matrix

`vpnd probe-matrix` runs a configurable (protocol × destination-class)
matrix sweep at a fixed poll interval over a fixed duration, and writes
a JSON report with per-cell verdicts, per-cell RTTs, and onset/recovery
windows per (protocol, destination-class) pair. Use it when you suspect
a filtering pipeline is applying policy at a level above per-protocol
fingerprinting — single-protocol probes miss the cross-protocol
simultaneity signal that this report is designed to surface.

## Why simultaneity

A filter that drops one protocol may be acting on that protocol's
fingerprint. A filter that drops several different protocols
*simultaneously* from the same vantage to the same destination ASN
bucket is acting at a higher layer (ASN, time-of-day window,
connection budget). The simultaneity matrix captures both views in
one run.

## Matrix dimensions

### Protocols (5)

| Slug | Probes |
|------|--------|
| `mtproto` | Telegram MTProto handshake |
| `xhttp-vless` | VLESS over XHTTP transport |
| `xhttp-trojan` | Trojan over XHTTP transport |
| `tcp-trojan` | Trojan over plain TCP |
| `tls-non-443` | Plain TLS handshake on any non-443 port |

### Destination classes (3)

Operators map actual destination IPs to classes in the config file.
The class names describe the *technical signature* of the destination
ASN bucket, not the operator or geography — this is a project-wide
rule (see root `CLAUDE.md` Hard rules).

| Class | Technical signature |
|-------|---------------------|
| `domestic-allowlisted` | Domestic ASN that historically clears filtering peering checks (no TCP-freeze treatment, no SNI-based diff). |
| `domestic-generic` | Domestic ASN with no specific allowlist treatment — baseline domestic path. |
| `foreign-non-allowlist` | Foreign-DC ASN bucket that historically triggers connection-freeze rules. |

### Time dimension

Poll interval defaults to **300 s (5 min)**. With the default 4-hour
run, that's **48 ticks × 5 protocols × 3 destinations = 720 cell
invocations** per run.

## Usage

```bash
# 4-hour sweep, 5-min poll interval, default config path
vpnd probe-matrix --duration 4h \
  --config vpnd/config/probe-matrix.yaml

# Faster smoke test — 30 min, 1-min poll
vpnd probe-matrix --duration 30m --poll-interval-seconds 60

# Print the call graph without running
vpnd --explain probe-matrix --duration 4h
```

The orchestrator owns the loop; per-cell probes shell out to
`make probe-matrix-cell` (script: `scripts/probe-matrix-cell.sh`).
The wrapper script is intentionally minimal today — it returns
`unknown` for every cell. Future PRs implement per-protocol probe
drivers behind the same JSON contract.

## Config file

```yaml
# vpnd/config/probe-matrix.yaml
vantage: "operator-supplied-label"
poll_interval_seconds: 300
protocols:
  - mtproto
  - xhttp-vless
  - xhttp-trojan
  - tcp-trojan
  - tls-non-443
destinations:
  - class: domestic-allowlisted
    endpoint: "10.0.0.1:443"
  - class: domestic-generic
    endpoint: "10.0.0.2:443"
  - class: foreign-non-allowlist
    endpoint: "203.0.113.1:443"
```

Operators supply actual IPs in `endpoint:`. The code carries no
addresses; the config file is the boundary between operator-owned
data and version-controlled tooling.

## Output schema

Reports land at `vpnd/state/probe-matrix-<unix-ms>.json` by default.
Schema (`schema_version: 1`):

```jsonc
{
  "schema_version": 1,
  "vantage": "string",
  "started_at_unix_ms": 1700000000000,
  "finished_at_unix_ms": 1700001200000,
  "poll_interval_seconds": 300,
  "cells": [
    {
      "timestamp_unix_ms": 1700000000000,
      "protocol": "mtproto",
      "destination_class": "domestic-allowlisted",
      "endpoint": "10.0.0.1:443",
      "verdict": "ok",         // ok | throttled | blocked | unknown | error
      "rtt_ms": 42,             // optional
      "error_kind": null        // populated when verdict == error
    }
    // ... one cell per (tick × protocol × destination)
  ],
  "windows": [
    {
      "protocol": "tcp-trojan",
      "destination_class": "foreign-non-allowlist",
      "onset_unix_ms": 1700001200000,   // first non-OK tick
      "recovery_unix_ms": null          // first OK tick after onset, or null if not seen
    }
    // ... one entry per (protocol, destination_class) pair
  ]
}
```

### Schema versioning

`schema_version` will bump on any breaking change to the cell or
window structs. Snapshot tests in `vpnd/tests/probe_matrix_snapshot.rs`
lock the shape — a PR that changes the schema must update the
snapshot in the same commit and the analysis tools downstream must
range-check `schema_version` before consuming.

## Interpreting the report

The interesting patterns to look for:

- **Simultaneity across protocols, single destination class** — if
  every protocol drops at the same tick for a `foreign-non-allowlist`
  destination, that's an ASN-level filtering signal independent of
  per-protocol fingerprint.
- **Simultaneity across destination classes, single protocol** — if
  a single protocol drops for every destination class at the same
  tick, that's a protocol-fingerprint filter active at the vantage.
- **Onset clusters** — multiple cells with onsets within one or two
  ticks of each other suggest a coordinated policy push. The
  `onset_unix_ms` field is the cheap way to spot this.
- **Recovery clusters** — `recovery_unix_ms` lines up across cells
  when policy backs off. If recovery times scatter, that's per-cell
  state (TCP-freeze recovery is connection-local), not a coordinated
  release.

## Limitations

- The per-cell probe drivers are stubs today. Every cell returns
  `unknown` until the protocol-specific probe logic is wired into
  `scripts/probe-matrix-cell.sh`. The orchestration framework, JSON
  schema, snapshot test, and onset/recovery analyser are all in
  place — the only thing missing is the actual per-protocol probe
  implementations.
- Probe traffic itself can become a DPI signature. Set
  `poll_interval_seconds` so the cell invocations stay below the
  rate a legitimate user would generate. 300 s is the default for
  that reason.
- One vantage is one observation. Cross-validate with OONI / an
  independent four-layer diagnostic (`docs/REGRESSION-BASELINE.md`)
  before promoting findings.
- Time correlation across cells is only as good as the runner's
  clock. Avoid running through a host with NTP drift; the report's
  `timestamp_unix_ms` is from the orchestrator's local clock.
