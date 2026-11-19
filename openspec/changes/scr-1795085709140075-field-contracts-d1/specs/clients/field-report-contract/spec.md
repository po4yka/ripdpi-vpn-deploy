## Purpose

Define the canonical anonymous client field-report v1 contract and the ripdpi-bundle v3 contract that carry client-observed health and server-published health between the server and the client.

## ADDED Requirements

### Requirement: REQ-REPORT-SHAPE — Field report v1 shape

The schema MUST accept only: `schema_version` 1; `window` {`start_utc` rounded to the hour, `duration_hours` 1 to 24}; `client` {`app_version` as "major.minor", `platform` "android"}; `network` {`source` sim, server_hint or none; optional `operator` {`mcc`, `mnc`}; optional `asn` integer; optional `country` ISO-3166 alpha-2; `network_type` wifi, cellular or other}; and `buckets[]`. `additionalProperties` MUST be false at every object level.

#### Scenario: field report v1 shape

- **WHEN** the golden report is validated and a copy with an extra property at any level is validated
- **THEN** the golden report passes and every extra-property copy is rejected

### Requirement: REQ-REPORT-NETWORK-SOURCE — The network identity has one named source

The client MUST NOT look up its ASN or public address on the device. `network.source` MUST be `sim`, `server_hint` or `none`, and a report MUST carry only the identity of its source: `operator` for `sim`, `asn` for `server_hint`, neither for `none`. A `sim` report MUST have `network_type` cellular. `country` MAY appear with any source.

#### Scenario: the network identity has one named source

- **WHEN** a report has no `source`, an unknown `source`, `sim` without `operator` or with `asn` or on wifi, `server_hint` without `asn` or with `operator`, or `none` with `asn` or `operator`
- **THEN** the validator rejects each, and the `sim` and `server_hint` goldens pass

### Requirement: REQ-REPORT-OPERATOR — Operator code shape

`network.operator` MUST hold only `mcc` (3 digits) and `mnc` (2 or 3 digits), both strings. The strict validator MUST reject a trailing newline and a number in place of a digit string.

#### Scenario: operator code shape

- **WHEN** a report has an extra `operator` property, a 2-digit MCC, a 4-digit MNC, an MNC with a trailing newline, or an MCC number
- **THEN** the validator rejects each for its named constraint

### Requirement: REQ-NETWORK-HINT — Client network hint v1

`contract/client-network-hint.schema.json` MUST accept only `schema_version` 1, `asn` integer 1 to 4294967295, `country` ISO-3166 alpha-2, `observed_at` rounded to the hour and `ttl_seconds` 300 to 86400, with `additionalProperties` false. The hint MUST NOT carry the request address. The documentation MUST state that the client fetches the hint directly outside the tunnel with the cohort token and discards a hint fetched through the tunnel.

#### Scenario: client network hint v1

- **WHEN** the golden hint and copies with an extra address property, a sub-hour `observed_at`, a float `asn`, a `country` with a trailing newline, a `ttl_seconds` under 300 or `schema_version` 2 are validated
- **THEN** the golden passes and each copy is rejected for its named constraint

### Requirement: REQ-REPORT-BUCKET — Bucket fields and failure stage

Each bucket MUST carry `server_ref` (opaque bundle endpoint id), `protocol` (vless-reality, xhttp, hysteria2, amneziawg, naiveproxy or local-desync), `outcome` (success or failure), `attempts` and `latency_ms_histogram` with fixed upper bounds [50,100,250,500,1000,2500,5000,+Inf]. `failure_stage` (dns, tcp_connect, tcp_reset, tls_handshake, reality_auth, quic_handshake, proxy_auth, protocol_error, idle_timeout, throttled or unknown) MUST be present if and only if `outcome` is failure.

#### Scenario: bucket fields and failure stage

- **WHEN** a failure bucket omits `failure_stage`, or a success bucket includes it, or the histogram has a different bound set
- **THEN** the validator rejects each of the three documents

### Requirement: REQ-REPORT-PRIVACY — Forbidden identifying data

The schema and fixtures MUST reject IP addresses, device or user IDs, subscription tokens, hostnames other than `server_ref`, and timestamps finer than the hour. The schema MUST use patterns and formats that fail an IPv4, IPv6, or hostname value in `server_ref`, and a `start_utc` with nonzero minutes or seconds.

#### Scenario: forbidden identifying data

- **WHEN** a report has `server_ref` "203.0.113.7", "node.example.org", or `start_utc` "2026-11-19T10:15:00Z"
- **THEN** validation fails for each

### Requirement: REQ-REPORT-MINBUCKET — Small bucket suppression is part of the contract

The schema MUST require `attempts` of at least 5 per bucket, and the contract documentation MUST state that the client suppresses buckets under 5 attempts.

#### Scenario: small bucket suppression is part of the contract

- **WHEN** a bucket has `attempts` 4
- **THEN** validation fails

### Requirement: REQ-BUNDLE-V3 — Bundle v3 replaces v2

`contract/ripdpi-bundle.schema.json` MUST set `schema_version` const 3 and MUST reject a v2 document. Each endpoint MUST allow `health` {`status` healthy, degraded, down or unknown; `observed_at` RFC3339; `ttl_seconds`}. The bundle MUST allow a top-level `field_report` {`endpoint` https URL, `cohort_token`, `max_reports_per_day`, optional `network_hint_endpoint` https URL}. All objects MUST set `additionalProperties` false.

#### Scenario: bundle v3 replaces v2

- **WHEN** the v2 golden bundle and v3 bundles with an http `field_report.endpoint` or an http `network_hint_endpoint` are validated
- **THEN** the v2 bundle is rejected on `schema_version`; both http endpoints are rejected; the v3 golden with an https `network_hint_endpoint` passes

### Requirement: REQ-BUNDLE-HEALTH-TTL — Expired health is unknown

The documentation and a fixture MUST define that a client treats a `health` whose `observed_at` plus `ttl_seconds` is in the past as `unknown`.

#### Scenario: expired health is unknown

- **WHEN** a golden fixture has `observed_at` older than `ttl_seconds`
- **THEN** `docs/reference/ripdpi-bundle.md` states the unknown rule and the fixture is marked as the expiry case
