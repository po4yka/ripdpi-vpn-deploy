## Purpose

Define how the subscription host accepts, validates, limits and aggregates anonymous client field reports into bounded Prometheus metrics and alerts.

## ADDED Requirements

### Requirement: REQ-INGEST-VALIDATE — Schema validation and rejection codes

The endpoint MUST accept a POST whose body validates against `contract/client-field-report.schema.json` and whose `cohort_token` is accepted, and MUST respond 400 for schema failure, 401 for a bad cohort token, 413 for a body over the size limit and 429 when the rate limit is exceeded.

#### Scenario: schema validation and rejection codes

- **WHEN** a valid report, a report with an extra property, a bad token, a body over the limit and a burst over the rate limit are posted
- **THEN** the responses are 2xx, 400, 401, 413 and 429 respectively and only the first changes any metric

### Requirement: REQ-INGEST-NOIP — No IP in logs or labels

The endpoint MUST NOT write a client IP, device ID or token to any log line, metric label or stored file beyond the existing categorical log policy, and rate limiting MUST NOT persist an IP beyond the limiter window in memory.

#### Scenario: no ip in logs or labels

- **WHEN** a report is posted from a test address and the logs, the metrics output and the state directory are searched for that address and the token
- **THEN** no occurrence is found

### Requirement: REQ-INGEST-LABELS — Bounded metric labels

The aggregation MUST expose counters and a histogram with only the labels protocol, failure_stage, asn, country and server_ref; `asn` MUST be one of the configured top-N values else "other"; `server_ref` MUST be accepted only if it is in the current bundle endpoint list, else "other".

#### Scenario: bounded metric labels

- **WHEN** reports arrive for 1000 distinct ASNs and unknown `server_ref` values
- **THEN** the exported series count stays at or below the configured bound

### Requirement: REQ-INGEST-MINATTEMPT — Buckets under 5 attempts are dropped

The ingest MUST drop a bucket with fewer than 5 attempts even if a schema-valid report contains it, and MUST count the drop in a metric without identifying labels.

#### Scenario: buckets under 5 attempts are dropped

- **WHEN** a report holds one bucket with 4 attempts and one with 5
- **THEN** only the bucket with 5 attempts changes the aggregate

### Requirement: REQ-INGEST-ALERT — Failure-rate alert by protocol and ASN

The alert rules MUST include a rule that fires when the client failure ratio for a protocol and ASN exceeds the configured threshold over the window with at least the configured attempts, and a promtool test MUST prove the firing and non-firing cases.

#### Scenario: failure-rate alert by protocol and asn

- **WHEN** promtool replays a series with 60 percent failures for one protocol and ASN and one with 5 percent
- **THEN** the first fires and the second does not

### Requirement: REQ-INGEST-SECREVIEW — Security review is recorded

The verification file MUST record the `security-review` skill result for the endpoint covering authentication, abuse limits, input validation, log content and denial of service.

#### Scenario: security review is recorded

- **WHEN** the change enters review
- **THEN** `verification.md` names the review result and each finding is resolved or tracked
