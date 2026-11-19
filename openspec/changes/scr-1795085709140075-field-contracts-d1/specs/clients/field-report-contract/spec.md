## Purpose

Define the canonical anonymous client field-report v1 contract and the ripdpi-bundle v3 contract that carry client-observed health and server-published health between the server and the client.

## ADDED Requirements

### Requirement: REQ-REPORT-SHAPE — Field report v1 shape

The schema MUST accept only: `schema_version` 1; `window` {`start_utc` rounded to the hour, `duration_hours` 1 to 24}; `client` {`app_version` as "major.minor", `platform` "android"}; `network` {`asn` integer, `country` ISO-3166 alpha-2, `network_type` wifi, cellular or other}; and `buckets[]`. `additionalProperties` MUST be false at every object level.

#### Scenario: field report v1 shape

- **WHEN** the golden report is validated and a copy with an extra property at any level is validated
- **THEN** the golden report passes and every extra-property copy is rejected

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

`contract/ripdpi-bundle.schema.json` MUST set `schema_version` const 3 and MUST reject a v2 document. Each endpoint MUST allow `health` {`status` healthy, degraded, down or unknown; `observed_at` RFC3339; `ttl_seconds`}. The bundle MUST allow a top-level `field_report` {`endpoint` https URL, `cohort_token`, `max_reports_per_day`}. All objects MUST set `additionalProperties` false.

#### Scenario: bundle v3 replaces v2

- **WHEN** the v2 golden bundle and a v3 bundle with an http `field_report.endpoint` are validated
- **THEN** the v2 bundle is rejected on `schema_version`; the http endpoint is rejected; the v3 golden passes

### Requirement: REQ-BUNDLE-HEALTH-TTL — Expired health is unknown

The documentation and a fixture MUST define that a client treats a `health` whose `observed_at` plus `ttl_seconds` is in the past as `unknown`.

#### Scenario: expired health is unknown

- **WHEN** a golden fixture has `observed_at` older than `ttl_seconds`
- **THEN** `docs/reference/ripdpi-bundle.md` states the unknown rule and the fixture is marked as the expiry case
