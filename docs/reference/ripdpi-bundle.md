# RIPDPI Bundle — server-side schema specification

> **Status:** Current · **Type:** reference · **Tier:** — · **Reviewed:** 2026-11-19

> **The executable contract is [`contract/ripdpi-bundle.schema.json`](../../contract/ripdpi-bundle.schema.json)** — a JSON Schema (draft 2020-12) that is the single source of truth for the `ripdpi` object. This document is its prose companion. The schema is vendored byte-identical into the RIPDPI Android client repo and validated by a contract test in **both** CIs (`scripts/validate-bundle.py` + `tests/unit/test_bundle_schema.py` here; `RipdpiBundleContractTest` there), so the contract cannot drift silently between the two repos. When you change the shape of the `ripdpi` object, change the schema first.

## Overview

`emit-bundle.sh` (and `make emit-bundle CLIENT=<name>`) produces a single JSON file that is the canonical subscription artifact for the RIPDPI Android client. It uses the explicit RIPDPI profile format from `emit-singbox.sh`, extended with a top-level `ripdpi` object carrying device-VPN and transport-obfuscation metadata. Unlike the standard emitter output, this format includes P1 XHTTP, which the RIPDPI client implements but official sing-box does not.

Do not send this artifact to standard sing-box clients. They may reject the unknown top-level `ripdpi` field, and official sing-box rejects the XHTTP transport. Operators serving those clients must use the `/sub` plain endpoint.

## Top-level structure

```jsonc
{
  // --- RIPDPI profile format from emit-singbox.sh ---
  "log":       { ... },
  "dns":       { ... },
  "inbounds":  [ ... ],
  "outbounds": [ ... ],   // includes P0/P1/P2 + selector/urltest
  "route":     { ... },

  // --- RIPDPI extension ---
  "ripdpi": {
    "schema_version": 3,
    "amneziawg":      [ <AWGEntry>, ... ],
    "hysteria_extras": { "<tag>": <HysteriaExtras>, ... },
    "topology":       <Topology>,        // declares split-hop / realm relay
    "endpoints":      { "<server_ref>": { "health": <Health> }, ... }, // optional
    "field_report":   <FieldReport>,     // optional; absent when field reports are off
    "expires":        "2026-12-31T23:59:59Z", // optional; ISO-8601 UTC
    "migration":      <Migration>        // optional; device server migration receipt metadata
  }
}
```

The validator also checks protocol semantics without changing the JSON schema: AWG public and preshared keys use canonical base64 for exactly 32 bytes; endpoints have a valid host and port; addresses and allowed networks use valid CIDRs; junk bounds are ordered and header ranges do not overlap. DNS addresses, port-hop ranges and calendar expiry must be valid. Refusals report categories without credential values. Public examples use deterministic synthetic keys.

## `ripdpi.schema_version`

Integer. Currently `3`. The client rejects other versions. Version 3 adds `ripdpi.endpoints` (server-observed health per endpoint) and `ripdpi.field_report`, and rejects unknown fields at every level, the top level included. Version 2 carried AWG headers as canonical strings with the named wire profile; version 3 keeps that AWG shape.

**Breaking change:** version 3 replaces version 2. The schema and `scripts/validate-bundle.py` reject a version 2 bundle, and there is no compatibility shim or dual-version mode. A client that supports only version 2 refuses a version 3 bundle, so the paired RIPDPI release that vendors this schema must ship before fresh bundles are exported. Update the producer and consumer together, then export a fresh bundle. The `x-contract-version` schema field is the paired version pin. The nested payload-failover contract retains its own version.

## `ripdpi.endpoints`

Optional map from `server_ref` to per-endpoint metadata. A `server_ref` is the outbound or AWG tag of that endpoint in the same bundle (pattern `^[A-Za-z0-9_-]{1,64}$`, so it cannot hold an IP address or hostname); the validator refuses a key that names no outbound or AWG tag of a full bundle. Client field reports quote the same value. Each entry holds one required `health` object:

| Field | Type | Rule |
|---|---|---|
| `status` | string | `healthy`, `degraded`, `down` or `unknown`. |
| `observed_at` | string | RFC 3339 UTC instant (`Z` suffix) of the server-side observation, a valid calendar instant. |
| `ttl_seconds` | integer | 60 to 86400. |

**Expiry rule:** the client treats a `health` whose `observed_at` plus `ttl_seconds` is in the past as `unknown`, whatever `status` says. [`contract/ripdpi-bundle.health-expired.json`](../../contract/ripdpi-bundle.health-expired.json) is the expiry case: evaluated at its `_evaluated_at` instant, every endpoint is effectively `unknown`. The generator derives health from server-side liveness data; a missing or stale input is published as `unknown`.

**Generation:** Bundle emission, subscription issuance and subscription refresh publish `ripdpi.endpoints` when `BUNDLE_HEALTH_FILE` names a health configuration. Refresh the published subscription to deliver a new snapshot on the client's next fetch. The delivery drift check compares configuration and credentials independently of these expiring observations. The configuration is a JSON object with these optional keys:

| Key | Default | Meaning |
|---|---|---|
| `liveness` | none | Path to a `scripts/protocol-liveness.py` result, normally `last-evidence.json` in its state directory. |
| `policies` | `{}` | Map from bundle host (`provider:environment`) to its liveness policy id. |
| `cascade_leg_health` | `{}` | Map from bundle host to a cascade leg health record checked by `scripts/check-cascade-leg-health.py`. |
| `max_age_seconds` | `1800` | Evidence older than this is ignored. |
| `ttl_seconds` | `900` | Published `ttl_seconds`; generation fails when it exceeds `max_ttl_seconds`. |
| `max_ttl_seconds` | `86400` | Operator ceiling for `ttl_seconds`, at most the contract maximum. |
| `min_failed_vantages` | `2` | Blocked vantages that make an endpoint `down`. |

The tag prefix selects the sentinel profile (`p0-reality-`, `p1-xhttp-`, `p2-hysteria2-`; AWG entries use `p2-amneziawg`). The generator matches each non-AWG endpoint to its exact `server_ref` in the sentinel evidence. In a v3 bundle the alternate XHTTP tag starts with `p1-xhttp-_alternate-`. With fresh evidence for the host's policy, `down` means at least `min_failed_vantages` vantages saw the endpoint blocked, `healthy` means every fresh matching observation reports `ok`, and any other mix with a working or blocked vantage is `degraded`. No fresh matching evidence, no policy for the host, a transport without a sentinel profile, or a configured cascade leg that is not proven healthy gives `unknown`. `observed_at` is the newest fresh observation, or the generation time for `unknown` without one.

## `ripdpi.field_report`

Optional opt-in configuration for anonymous client field reports. Absent when the operator has not enabled field reports. The generator copies `endpoint`, `cohort_token`, `max_reports_per_day` and the optional `network_hint_endpoint` from the SOPS key `field_report` when `field_report.enabled` is true; the previous token never reaches a bundle. All fields except `network_hint_endpoint` are required:

| Field | Type | Rule |
|---|---|---|
| `endpoint` | string | `https://` URL without userinfo, whitespace or fragment; plain `http` is rejected. |
| `cohort_token` | string | 22 to 64 base64url characters. One token is shared by every device of a cohort and never derives from a device identity. |
| `max_reports_per_day` | integer | 1 to 24. |
| `network_hint_endpoint` | string | Optional. `https://` URL of the [network hint](#client-network-hint-v1), same rules as `endpoint`. Absent: the client sends only `network.source` `sim` or `none`. |

## Client field report v1

[`contract/client-field-report.schema.json`](../../contract/client-field-report.schema.json) is the canonical contract for one report, checked by `scripts/validate-field-report.py`. [`contract/client-field-report.golden.json`](../../contract/client-field-report.golden.json) is the golden `server_hint` report and [`contract/client-field-report.golden-sim.json`](../../contract/client-field-report.golden-sim.json) the golden `sim` report; `contract/negative/report-*.json` are the rejected cases. RIPDPI vendors the schema and fixtures byte-identically. Every object sets `additionalProperties: false`.

| Field | Rule |
|---|---|
| `schema_version` | `1`. |
| `window.start_utc` | UTC instant rounded down to the hour: minutes and seconds are `00`. |
| `window.duration_hours` | 1 to 24. |
| `client.app_version` | `major.minor` only. |
| `client.platform` | `android`. |
| `network.source` | Required. Where the network identity came from: `sim`, `server_hint` or `none`. |
| `network.operator` | `{mcc, mnc}`: MCC 3 digits, MNC 2 or 3 digits, both strings. Only with `source` `sim`. |
| `network.asn` | Integer 1 to 4294967295. Only with `source` `server_hint`, where it is required. |
| `network.country` | Optional. ISO 3166-1 alpha-2, upper case. |
| `network.network_type` | One of three link classes, listed below the table. |
| `buckets[]` | 1 to 256 buckets. |

The `network_type` values are `wifi`, `cellular` and `other`.

The client never looks up its own ASN or public address. The network identity comes from one source, named by `network.source`:

- `sim`: the SIM or registered network operator code (`TelephonyManager`, no network request). It requires `operator`, forbids `asn` and requires `network_type` `cellular`, because the SIM code does not describe a Wi-Fi path.
- `server_hint`: the `asn` (and usually `country`) of a fresh [network hint](#client-network-hint-v1). It requires `asn` and forbids `operator`.
- `none`: no identity. It forbids both `asn` and `operator`.

The schema enforces these rules with `if`/`then` on `network.source`; `contract/negative/report-*source*`, `report-sim-*`, `report-server-hint-*`, `report-none-*` and `report-operator-*` are the rejected cases.

Each bucket has `server_ref` (the bundle `endpoints` key), `protocol` (`vless-reality`, `xhttp`, `hysteria2`, `amneziawg`, `naiveproxy` or `local-desync`), `outcome` (`success` or `failure`), `attempts` and `latency_ms_histogram`. `failure_stage` is present if and only if `outcome` is `failure`; it is one of `dns`, `tcp_connect`, `tcp_reset`, `tls_handshake`, `reality_auth`, `quic_handshake`, `proxy_auth`, `protocol_error`, `idle_timeout`, `throttled` or `unknown`.

`latency_ms_histogram` is an array of exactly 8 attempt counts aligned with the fixed upper bounds 50, 100, 250, 500, 1000, 2500, 5000 and +Inf milliseconds (`x-latency-bounds-ms` in the schema). The counts sum to `attempts`; the validator checks this sum because the schema cannot express it.

**Small-bucket suppression:** the client suppresses every bucket with fewer than 5 attempts, and the schema rejects `attempts` below 5.

### Upload and ingest

The client sends one report as `POST` to `field_report.endpoint` with `Content-Type: application/json` and the header `Authorization: Bearer <cohort_token>`. The token is never part of the body or the URL. The subscription-host ingest (`ansible/roles/subscription-host/files/vpn-field-report.py`, enabled by `subscription_field_report.enabled`) answers with these status codes:

| Status | Meaning |
|---|---|
| `202` | Accepted and aggregated. The report is then discarded. |
| `400` | The body is not JSON or fails `scripts/validate-field-report.py`. |
| `404` | The token is neither the current cohort token nor the previous one inside its overlap, the method is not `POST`, or the route is off. The vhost gives the same answer as for any unknown path, so a bad token or method does not show that the route exists; `400`, `413` and `429` still do, which is accepted because the path is published in every bundle. The client discards the report and sends no more until it has a new bundle. |
| `413` | The body is larger than `subscription_field_report.max_body_bytes`. |
| `429` | The per-address nginx rate is exceeded. The ingest has no second rate limit. |

The whole report is validated first; an invalid report changes no counter. In an accepted report, a bucket under `subscription_field_report.min_attempts` attempts (5 or more) is dropped and counted in `vpn_field_report_dropped_buckets_total`, and the rest is aggregated. Because the contract already rejects a bucket under 5 attempts, a report that holds one is refused with `400`. Every `pattern` anchors at the end of input as in ECMA-262: the validator does not accept a trailing newline that Python's `$` would admit. The ingest exports only aggregate counters with the labels `protocol`, `failure_stage`, `network`, `country` and `server_ref`. `network` is `<mcc>-<mnc>` for a `sim` report, `as<asn>` for a `server_hint` report and `unknown` for `none`; `country` is `unknown` when the report has none. Each keeps its value only when it was in the top N of the previous window (operators `operator_top_n` 20 and ASNs `asn_top_n` 20 rank separately, `country_top_n` 10), otherwise `other`; `server_ref` keeps its value only when it is in `subscription_field_report.server_refs`, otherwise `other`. A label-set budget (`max_series`) folds further new sets into `other`. No address, token or body is written to a log, a metric or a file.

## Client network hint v1

[`contract/client-network-hint.schema.json`](../../contract/client-network-hint.schema.json) is the canonical response of `GET field_report.network_hint_endpoint`; [`contract/client-network-hint.golden.json`](../../contract/client-network-hint.golden.json) is the golden hint and `contract/negative/hint-*.json` are the rejected cases. The client sends the request with `Authorization: Bearer <cohort_token>` directly over the device network, not through the tunnel, at the same time it fetches the bundle. It discards a hint that was fetched through the tunnel, because that hint names the VPN node's network; the server also answers `204` when the request comes from a public address of a fleet node, which catches a tunnelled fetch that leaves through a fleet node. Point `network_hint_endpoint` at a separate subscription-only host: the fetch leaves the device outside the tunnel, so its destination is visible on the device network. The client adds random jitter to the fetch so it does not follow the bundle fetch at a fixed offset.

| Field | Rule |
|---|---|
| `schema_version` | `1`. |
| `asn` | Integer 1 to 4294967295. |
| `country` | ISO 3166-1 alpha-2 registration country of the ASN, upper case. |
| `observed_at` | Lookup time in UTC, rounded down to the hour. |
| `ttl_seconds` | 300 to 86400. After `observed_at` plus `ttl_seconds` the client stops using the hint and sends `source` `sim` or `none`. |

The subscription host answers `200` with this body, `204` with no body when the request address has no routed ASN in its offline dataset or is a fleet node's public address (for an IPv6 node, any address in its /64), `404` (the vhost's uniform not-found answer) for an unknown token, a method other than `GET`, a disabled hint or a dataset that failed to load, `400` when the request carries a client forwarding header, and `429` over the per-address rate. The response never holds the request address. Any answer other than `200` means no hint: the client sends `source` `sim` or `none`.

On the server, `subscription_field_report.network_hint.enabled` adds the route to the field-report ingest (same process, same cohort tokens; the ingest must be enabled). nginx passes the TCP peer address `$remote_addr` to the ingest in its own `X-Network-Hint-Peer` header, replaces any client copy of that header, sends no `X-Forwarded-For`, `Forwarded` or `X-Real-IP`, and refuses with `400` a request that carries any of them; the vhost sets no `real_ip` module directive, so a client cannot choose the address that is looked up. A CDN or reverse proxy in front of the subscription host would make every hint name the proxy's network, so the hint is only correct on a directly reached host. The ingest looks the address up in memory and drops it: it is never logged, counted or stored. The lookup uses the pinned offline dataset IPtoASN `ip2asn-combined.tsv.gz` (Public Domain Dedication and License 1.0, recorded in `ansible/roles/subscription-host/THIRD_PARTY_NOTICES.md`). `scripts/refresh-ip-asn-dataset.sh` downloads a new copy into the ignored `.cache/ip-asn/` directory, checks that the ingest loads it and prints the `dataset_version` and `dataset_sha256` to pin; deploy verifies the controller file against that pin and copies it, and the ingest checks the SHA-256 again at start. No host fetches the dataset. Ranges with AS 0 (not routed) or without a two-letter country give `204`.

**Forbidden data:** a report never carries an IP address, a device or user identifier, a subscription token, a hostname or a timestamp finer than the hour. The schema rejects them: no field can hold them, and `server_ref` and `start_utc` patterns reject an IPv4, IPv6 or hostname value and nonzero minutes or seconds. Validator diagnostics name the failed constraint and its path, never the rejected value.

## `ripdpi.payload_failover`

Optional payload health and quality policy for the RIPDPI imported selector runtime. Set `client_payload_failover` in the contributing Ansible group/profile variables; every selected host must resolve to the same policy. The emitter refuses conflicting policies or a policy without proxy candidates. Standard sing-box exports do not include this field: their `urltest` remains a HEAD/RTT check, which does not establish useful payload transfer.

```yaml
client_payload_failover:
  schema_version: 2
  selector_tag: select
  probes:
    - url: https://control-a.example.test/__throttle_probe?bytes=262144
      expected_bytes: 262144
      sha256: b1882646e3ee80170bd9207304f77c71d388b0a786d53e5e7f4e16fb22e8b6dc
    - url: https://control-b.example.test/__throttle_probe?bytes=262144
      expected_bytes: 262144
      sha256: b1882646e3ee80170bd9207304f77c71d388b0a786d53e5e7f4e16fb22e8b6dc
  interval_seconds: 60
  timeout_seconds: 10
  failure_threshold: 2
  recovery_threshold: 2
  cooldown_seconds: 120
  max_backoff_seconds: 900
  quality:
    max_pass_bytes: 2097152
    max_window_bytes: 16777216
    window_seconds: 3600
    minimum_gain_percent: 20
    maximum_loaded_latency_increase_ms: 50
```

Replace both illustrative URLs with separately operated HTTPS origins serving the exact canonical body described in [the probe runbook](../how-to/payload-throttle.md). These example domains are not working services. The repository does not enable this policy by default. Provisioning and accepting control origins is a separate live operation. HTTPS certificate verification remains required; redirects, short bodies and digest mismatches do not pass. A successful control can qualify a candidate when the other control is unavailable; failure requires both controls to fail through that same candidate.

Each probe requires 32768–1048576 bytes and a lowercase SHA-256 digest. Origins must differ after host/port normalization. URLs are ASCII HTTPS without userinfo or fragments. Bounds are: interval 30–3600 seconds, per-control timeout 1–30, failure/recovery thresholds 2–10, cooldown 30–3600, maximum backoff 60–3600. Timeout cannot exceed the interval; maximum backoff cannot be below it. Unknown fields and invalid input refuse the policy instead of silently dropping it.

The nested policy accepts only version 2; version 1 must be migrated before refresh. The nested version is independent of the enclosing bundle version. Omitting `quality` retains health-only selection. With quality enabled, each origin must also answer HEAD with status 200 and its exact Content-Length. Baseline and loaded request latency include the complete control transaction; neither is RTT. Verified GET body bytes divided by positive monotonic body duration establish goodput. Loaded latency requires a concurrent HEAD fully inside that body interval. A fast transfer may produce partial evidence, which cannot promote a candidate on quality alone.

Quality bounds are: pass allowance 65538–16777216 bytes, window allowance 65538–268435456 bytes, window duration 60–86400 seconds, minimum gain 5–100 percent and allowed loaded-latency increase 0–2000 ms. The window allowance must cover the pass allowance and its duration must cover the probe interval. The pass allowance must cover twice the sum of both `expected_bytes + 1` reservations. Reservations precede network I/O, survive failures, cancellation, restart, network and policy changes, and expire conservatively after reboot. They bound application body bytes, not TLS, tunnel or retransmission overhead.

A pass compares the active member and one rotating challenger using the same origin. Promotion requires repeated complete measurements: either the required goodput gain without exceeding the loaded-latency allowance, or a loaded-latency reduction meeting the same percentage threshold with non-regressing goodput. Existing recovery threshold and cooldown still apply. Partial, stale or deferred evidence stays visible without authorizing a quality switch. Ordinary health recovery still requires verified payload reachability; all-candidate failure retains the last proxy and never selects direct. REALITY uses the existing Xray candidate runtime; AWG is outside this selector pool. Plain sing-box URLTest remains RTT-only.

This policy applies to full imported selector profiles; the simple seeded-profile import surface explicitly refuses it. Upgrade the paired recipient before publishing version 2. The paired `contract/ripdpi-bundle.payload-failover.json` fixture contains synthetic emitted input for parser agreement, not live acceptance evidence. No policy or control endpoint is deployed by this change.

The [deployment snapshot](deployment-status.md#transport-activation) records the current dated activation result. Merging the producer and consumer, building an APK or deploying server code does not enable this optional policy. Install the paired client, accept both owned origins, export a fresh per-device bundle and verify useful traffic plus failure/recovery on that client before claiming live payload failover. The [probe runbook](../how-to/payload-throttle.md) defines the control body and path checks.

## `ripdpi.amneziawg`

Array of AWG device-VPN entries.  Empty array (`[]`) when AmneziaWG is not enabled for the selected profiles. Enabled AWG requires a unique bound device under `amneziawg_secrets.instances[].peers`; absence refuses the whole payload. Use `AWG_HOST=provider:env` for multiple enabled hosts and `AWG_INSTANCE=name` for multiple matching instances. The endpoint and parameters come from that instance, using the same resolver as the standalone and liveness clients.

### AWGEntry fields

```jsonc
{
  "tag":     "p2-awg-<client>",      // stable identifier; matches naming convention
  "address": ["10.66.66.2/32", "fd42:42:42::2/128"], // typed device identities, IPv4 then IPv6
  "dns":     ["1.1.1.1", "1.0.0.1"],
  "mtu":     1420, // integer 1280..1420, resolved once for every consumer

  // AmneziaWG obfuscation parameters — must match the server awg0.conf exactly.
  // Resolved with three-level precedence (SOPS > cohort YAML > hard default):
  //   jc=4  jmin=40  jmax=70  s1=50  s2=100  (H1..H4 have no hard default)
  "wire_profile": "awg-3.1-ranges-v1",
  "jc":   4,
  "jmin": 40,
  "jmax": 70,
  "s1":   50,
  "s2":   100,
  "h1":   "1000-1999",
  "h2":   "2000-2999",
  "h3":   "3000-3999",
  "h4":   "4000-4999",

  // I1..I5 are bounded canonical tag programs.
  // Present only when configured in SOPS or the cohort YAML; omitted when absent.
  "i1": "<b 0xaabb><r 8><rd 2><rc 2><t>",   // optional
  // ... i2..i5 follow the same rule

  // Fingerprint of the resolved obfuscation parameter set above (see below).
  "cohort_fingerprint": "sha256:<64-hex>",

  // The bundle carries no client private key. An operator recovery copy is encrypted in SOPS.
  // This flag tells the RIPDPI client to substitute the locally-stored key.
  "private_key_placeholder": true,

  "peer": {
    "public_key":           "<server WireGuard public key>",
    "preshared_key":        "<per-peer PSK from SOPS>",
    "endpoint":             "<server_ipv4>:<listen_port>",
    "allowed_ips":          ["0.0.0.0/0", "::/0"],
    "persistent_keepalive": 25
  }
}
```

Header ranges must be disjoint unsigned 32-bit intervals. Singletons from 0 through 4 are legal only for their own standard message type; other ranges start above 4. Use one decimal value for a singleton, with no leading zero. Programs use `<b 0x...>` with lowercase even-length hex, `<r N>` for arbitrary bytes, `<rd N>` for ASCII digits, `<rc N>` for ASCII letters, and `<t>` for the four-byte big-endian Unix timestamp. Programs contain at most 4096 characters, 64 tags, and 1280 output bytes. Each count is positive. Spaces occur only inside tags as shown. S3/S4 remain zero. Header protection, custom timers, content padding, random trailers, and disabled cookies are outside this profile.

The server admits ranges and signatures only for the reviewed source pair in `tests/integration/awg_source_candidate/sources.json`. That source remains a candidate; local interoperation does not establish production or physical-device eligibility. Native `.conf` files carry the supported wire fields and omit the JSON profile marker.

### Cohort fingerprint

`cohort_fingerprint` is a SHA-256 over the resolved AWG obfuscation parameter set for this entry — the values the client and the server `awg0.conf` **must agree on byte-for-byte** or the AmneziaWG handshake stalls / fails. It lets the client detect that disagreement *before* connecting and tell the user "profile outdated, refresh your subscription", instead of surfacing a silent stall (per `docs/reference/awg-cohorts.md`, a cohort mismatch shows up as "occasionally stalls, 3–4 retries" in the lucky case and a full handshake failure in the unlucky one).

Canonical pre-image (UTF-8, no trailing newline):

```
wire_profile=awg-3.1-ranges-v1&jc=<jc>&jmin=<jmin>&jmax=<jmax>&s1=<s1>&s2=<s2>&h1=<h1>&h2=<h2>&h3=<h3>&h4=<h4>&i1=<i1>&i2=<i2>&i3=<i3>&i4=<i4>&i5=<i5>
```

Each scalar is base-10 with no leading zeros. Each header is a canonical singleton or closed range string. Each `i`-value is its canonical tag program, or the empty string when absent. The fingerprint is `"sha256:" + hex(sha256(pre-image))`. The **one** implementation is `scripts/ripdpi_cohort_fingerprint.py` (called by `emit-bundle.sh` and pinned by the contract test); the client reimplements the identical algorithm and `contract/cohort-fingerprint.golden.json` — committed identically in both repos — guarantees the two implementations agree.

### Private-key handoff

`scripts/new-client.sh` generates the client private key and stores it in the SOPS-encrypted `client_registry.<device>.awg_private_key` field. The command emits enrollment metadata, not a plaintext key or a ready-to-import AWG file. The standalone `emit-awg.sh` configuration contains the literal `PrivateKey = <CLIENT_PRIVATE_KEY>`. The bundle also carries no key. `private_key_placeholder: true` tells the RIPDPI client to use its secure local key store. A new device needs a separate manual key handoff before AWG can connect.

For an authorized handoff, the operator selects the device's encrypted registry entry through the existing private SOPS recovery process. Check its exact provider, environment and instance binding and verify that the public key derived from this private key matches that instance's device peer. Deliver only the selected device key through an approved encrypted out-of-band channel or an in-person QR scan. Keep plaintext out of terminal recordings, agent sessions, logs and shared documents. For a standalone client, replace the placeholder only in the private recipient copy before import; for RIPDPI, import the key into the device's secure local store.

The current issuer does not automate this handoff or create plaintext files under `secrets/local/clients/**`. After delivery, the device-local key is primary; the encrypted registry copy permits recovery without rotating the peer. Never put the client private key into a distributed bundle or commit it.

An operator may validate a locally materialized Android artifact without relaxing the distribution contract:

```bash
python3 scripts/validate-bundle.py --runtime-materialized /path/to/embedded-relay-bundle.json
```

This explicit mode validates each inline AmneziaWG private key, removes it only from an in-memory copy, and then applies the unchanged redacted schema. It does not print the key, rewrite the artifact, or make the materialized file suitable for distribution. The file must be an owner-controlled regular file with mode `0600`, and every component of its path must be free of symlinks and unsafe writable directories. This local, transient artifact is the narrow exception to the SOPS input gate; remove it immediately after validation.

### Private-key recovery flow

`private_key_placeholder: true` means the bundle carries **no usable private key**. The client substitutes the device-local key. This section specifies what the client does when that local key is *not* available — first launch after a fresh install, a device migration, a cleared app data store, or a key the user never imported. Without a spec the client "closes the gap however" and may fail deep in AWG config parsing with an opaque error.

The client resolves the key in this order and surfaces one of these states (stable string codes the diagnostics layer and UI key off; they are part of the contract):

| State / code | Condition | Client behaviour |
|---|---|---|
| `KEY_PRESENT` | `private_key_placeholder=true` **and** a local key for this peer exists | Use it; connect normally. |
| `KEY_MISSING_REPROVISION` | placeholder `true`, no local key found | Do **not** fail in the parser. Import the profile in a disabled state and prompt: "This profile needs your AmneziaWG private key — re-import it (QR / Signal) to activate." The subscription itself remains valid. |
| `KEY_REJECTED` | a local key exists but the server rejects the handshake (wrong/rotated key) | Surface "key no longer matches this server — request re-provisioning"; keep the profile, do not delete it. |
| `PLACEHOLDER_ABSENT_NO_KEY` | `private_key_placeholder` is absent/false **and** no inline `private_key` | Treat as a malformed AWG entry and skip it (existing lenient-parser behaviour). |

The recovery action for `KEY_MISSING_REPROVISION` / `KEY_REJECTED` is the same out-of-band channel as the initial handoff: the operator retrieves the key from its existing device-local store or the SOPS recovery copy, checks the current binding and peer key, then follows the manual handoff above. Recovery of the same current key does not change the bundle. If the peer was rotated or revoked, use the current provisioning contract instead of restoring an old key.

## `ripdpi.hysteria_extras`

Object keyed by the exact Hysteria2 outbound `tag` that `emit-singbox.sh` emits for this host (`"p2-hysteria2-<provider>-<env>"`).  Empty object (`{}`) when Hysteria is not enabled or has no extras to convey.

The RIPDPI client uses these extras to configure transport-layer properties that the standard sing-box Hysteria2 outbound schema does not expose in the subscription format.

### HysteriaExtras fields

```jsonc
{
  // Always present.
  "insecure": false,

  // Present only when hysteria.salamander_enabled = true in SOPS.
  "obfs": {
    "type":     "salamander",
    "password": "<hysteria.salamander_password from SOPS>"
  },

  // The upstream Hysteria2 release whose Salamander algorithm this server runs
  // (= hysteria.version from SOPS).  Present only alongside salamander obfs.
  "salamander_upstream_tag": "v2.9.0",

  // Hopping policy for the qualified native RIPDPI client.
  // ports is the range string "low:high"; interval is the hop cadence.
  "port_hopping": {
    "ports":    "20000:50000",
    "interval": "30s"
  }
}
```

`insecure: false` is always present and non-negotiable.  The RIPDPI client treats a missing or `true` value as a configuration error and refuses to connect.

`salamander_upstream_tag` lets the client compare the server's Salamander algorithm version against the one its bundled obfuscator implements. Salamander can change between Hysteria2 releases; on a skew the client warns the user ("obfuscation may not match this server — update the app") instead of failing the handshake opaquely. It reuses the existing `hysteria.version` secret — no new key to keep in sync.

## `ripdpi.topology`

Declares the transport topology the client cannot infer from the flat `outbounds` list, so it can tell a split-hop or realm-relayed endpoint from a direct one rather than mis-modelling a dual-role flow.

```jsonc
{
  // true when this endpoint is the entry of a two-VPS split-hop topology
  // (entry and egress are different hosts). The client must NOT assume the
  // egress IP equals the endpoint IP — relevant against per-IP DPI classifiers.
  "split_hop_egress": false,

  // realm/relay id when the Hysteria2 endpoint is reached via a STUN/NAT
  // realm relay rather than directly; null when direct.
  "hysteria_realm": null
}
```

`split_hop_egress` is `false` for every emitted bundle. The split-hop ingress responder routes only the research probe runtimes through Node B; the family transports on that host still exit from the entry IP, so the flag must not claim otherwise until a family transport is routed through Node B. `hysteria_realm` remains explicit `vpn.hysteria_realm` metadata because the enable toggle alone does not define a stable realm identifier. Both default to the direct-deployment values (`false` / `null`). Pure egress roles (e.g. `warp-outbound`) are server-side only and intentionally absent — the client has no half to play there. Multi-host emission aggregates every entry rather than trusting `HOSTS` order: the first non-null realm identifier is retained, and conflicting non-null realm identifiers fail closed.

## `ripdpi.migration`

Optional object that carries device server-migration receipt metadata. The producer is the device-migration workflow in [Device migration](../how-to/device-migration.md), not `emit-bundle.sh`. The schema accepts the object and rejects unknown fields. All fields are required:

| Field | Type | Rule |
|---|---|---|
| `schema_version` | integer | Constant `1`. |
| `migration_id` | string | Lowercase UUID. |
| `delivery_id` | string | Lowercase UUID. |
| `target_tags` | array of strings | 1 to 128 unique tags. Each tag matches `^[A-Za-z0-9_.:-]{1,128}$`. |
| `receipt_key` | string | 64 lowercase hexadecimal characters. |
| `awg_previous_tags` | object | Up to 128 entries. Each key and value is a tag that matches the same pattern. |

## `ripdpi.expires`

Optional RFC-3339 / ISO-8601 UTC instant after which the subscription token stops serving this bundle (the server returns `410 Gone`). Carried **inside** the `ripdpi` object and atomic subscription document so the client can warn "subscription expires in N days, refresh" proactively, instead of only finding out when the next `/sub` fetch already failed.

`emit-bundle.sh` emits it when `BUNDLE_EXPIRES` is set. The supported issuance path normalizes `EXPIRES` once and writes the identical UTC instant into the authoritative subscription document (or legacy `.meta` sidecar) and the bundle's early-warning copy. Date-only input means midnight UTC. The field is absent for non-expiring tokens:

```bash
make issue-sub-token CLIENT=phone FORMAT=ripdpi EXPIRES=2026-12-31
```

## Merge guarantee

The `ripdpi` key is appended to the RIPDPI profile document via:

```bash
jq --argjson r "$ripdpi_json" '. + {ripdpi: $r}' base.json
```

All existing keys (`log`, `dns`, `inbounds`, `outbounds`, `route`) are preserved verbatim.  The merge does not modify, reorder, or re-encode any profile field.

## Usage

```bash
# Single host (default upcloud:prod)
make emit-bundle CLIENT=laptop

# Multi-host
HOSTS="upcloud:prod,hetzner:prod" make emit-bundle CLIENT=laptop

# With explicit cohort and AWG cohort slug
HOSTS="upcloud:p0,upcloud:p1p2" COHORTS="p0,p1p2" AWG_COHORT=narrow-junk-sequential \
  make emit-bundle CLIENT=phone

# Per-app routing flags are forwarded to the profile emitter
scripts/emit-bundle.sh phone --per-app-via-tun com.example.private
```

The output is written to stdout so the caller can redirect it, pipe it through a QR encoder, or POST it to a subscription host.

### Hysteria ECH and BBR recipient boundary

ECH-required Hysteria profiles currently target official sing-box 1.14.3 only. `emit-bundle` refuses them before output because the RIPDPI consumer has no qualified ECH parser/connection contract. The existing bundle schema/version is unchanged; public ECH configuration is never silently stripped. Use the canonical `emit-singbox` format for the supported ECH recipient. Private ECH keys never belong in either artifact. The new BBR recipient profiles use the same qualified official engine and also refuse RIPDPI export. The bandwidth-capped classical profile remains supported.


Hysteria port hopping requires the qualified native RIPDPI client. The emitter retains `hysteria_port_range` as standard `server_ports` and matching extras, with the same fixed `hop_interval`. The interval uses whole seconds, minutes or hours, from 5 seconds through 9223372036854 milliseconds. Invalid policy fails before output. The scalar `server_port` does not widen the hopping set. Older clients do not satisfy this contract. Official sing-box output retains its existing policy. Multi-host output includes extras for every Hysteria tag, independently of host order. Full bundle validation requires each hopping extra to match one Hysteria outbound by tag. When standard hopping fields are also present, their port set and effective interval must agree after normalization. Either policy form alone and standalone extension validation remain supported.

### Dual-stack device contract

AWG `address` contains exactly two canonical host CIDRs, IPv4 /32 followed by IPv6 /128. Encrypted peers use `allowed_ips.ipv4` and `allowed_ips.ipv6`; both must belong to their selected instance pools. The single-CIDR secrets contract is removed. `mtu` is an integer from 1280 through 1420, resolved from instance, technical cohort and role defaults. Both fields are required before publication. The wire array and schema version stay unchanged; consumers must adopt the stricter admission with the canonical vendored schema. Consumer integration is tracked by `po4yka/RIPDPI#DAT-1792081130689287`.
