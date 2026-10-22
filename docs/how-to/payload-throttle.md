# Exact payload probes

> **Status:** Current · **Type:** how-to · **Tier:** — · **Reviewed:** 2026-10-21

`make probe-payload-throttle` checks useful data on the selected client path.
Run it from that path, not from the VPN server. Every completed step requires
HTTP 200, the exact requested length and the canonical bytes below. A successful
handshake, empty HTTP 200, redirect or same-length error page cannot pass.

## Owned control endpoint

Run the bounded stdlib canary on loopback:

```sh
python3 scripts/serve-payload-probe.py --host 127.0.0.1 --port 8080
```

Place `/__throttle_probe` behind an existing operator-owned HTTPS reverse proxy,
forwarding query strings and POST bodies unchanged. Disable response compression
and caching for that route; retain ordinary TLS verification and bounded request
sizes/deadlines. The canary serves GET `?bytes=N`. POST requires `Content-Length:
N` and the canonical N-byte request body, then returns the same bytes. It rejects
chunked uploads, invalid sizes and incorrect content. Each connection has a
10-second total deadline, closes after the response, and the single worker
bounds concurrency. The default loopback bind is not public TLS termination.

Canonical content is the first N bytes of concatenated SHA256 digests of
ASCII `vpn-deploy-payload-v1:` followed by an unsigned eight-byte big-endian
counter starting at zero. Supported N is 1..65536. Both sides compute this
content independently; response headers are not evidence of body integrity.

Print exact hashes for recipient `payload_failover` controls:

```sh
python3 scripts/payload_probe_content.py --hashes 32768,65536
```

Each resulting `{expected_bytes, sha256}` pairs with an owned HTTPS URL such as
`https://control.example/__throttle_probe?bytes=32768`. Configure two independent
owned HTTPS origins in the recipient policy; this command does not deploy them
or qualify their availability.

## Client path selection

```sh
make probe-payload-throttle HOST=control.example ASN=AS64500
scripts/probe-payload-throttle.sh --host control.example --asn AS64500 \
  --sizes 1024,4096,16384,32768,65536 --socks-port 1080 --upload
```

`--socks-port` selects a loopback SOCKS5 endpoint and resolves the origin name
through SOCKS. It requires `--asn` so metadata lookup cannot issue direct
DNS/whois traffic. Failure never retries directly. Without it, curl explicitly uses
the current direct/TUN route. The probe ignores ambient proxy variables,
`NO_PROXY` and `.curlrc`; it never follows redirects. HTTPS is the default;
`--ca-file` selects an explicit owned CA when needed. `--scheme http` is for
local endpoint testing and does not provide authenticated origin identity.

`--upload` adds a POST at every size through the same selected path and verifies
the echoed body. `--timeout` bounds each transfer (1..30 seconds, default 15).
The ladder must contain 1..16 unique ascending sizes, each at most 65536 bytes.
Downloads are capped independently of Content-Length. Total worst-case transfer
time is the number of steps times the timeout, doubled with upload. Optional
ASN lookup has a separate 10-second budget; `--asn AS<number>` avoids it.

## Results and limits

The script emits exactly one JSON object with `verdict`, `rtt_ms`, `asn`,
`threshold_bytes` and `sizes`. Each size observation includes `bytes`,
`direction`, `completed`, `rtt_ms`, and a categorical `error_kind` on failure.
`rtt_ms` is the measured full transfer duration retained under the established
probe field name, not a separate network round-trip measurement.

- `ok`: every requested direction has small and large samples; all complete
  without a large-step time per byte at least three times the small-step median.
- `throttled`: a valid small baseline precedes a network completion cliff or
  time-per-byte spike at a size of at least 16384 bytes.
- `blocked`: no transfer completes and failures are network failures.
- `unknown`: incomplete ladder or failed small baseline with some success.
- `error`: malformed inputs, TLS verification, unexpected HTTP/content,
  dependency, lookup or local execution/persistence failure.

These are observed signatures. `blocked` and `throttled` do not establish a
censorship cause; origin failure and ordinary network faults can look similar.
Constant-rate transfers are not throttled merely because a larger body takes
longer. Download and upload use separate small-body rate baselines; zero-duration
samples cannot establish a timing slowdown.
The 16384-byte classification boundary is a diagnostic reference, not a universal
network rule. This standalone probe does not itself authorize rotation or bypass
the separate deployment acceptance checks.

State is an owner-only JSON file at
`${XDG_STATE_HOME:-$HOME/.local/state}/vpn-deploy/payload-throttle/AS<num>.json`.
A temporary sibling is atomically renamed after completion. `--no-state` disables
persistence. ASN/prefix are technical identifiers; organization/country strings
are never included. The optional daily operator cron remains an opt-in source
of actual probe traffic; avoid unbounded retries.
