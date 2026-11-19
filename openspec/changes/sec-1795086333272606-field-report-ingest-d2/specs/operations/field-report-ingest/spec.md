## Purpose

Define how the subscription host accepts, validates, limits and aggregates anonymous client field reports into bounded Prometheus metrics and alerts.

## ADDED Requirements

### Requirement: REQ-INGEST-VALIDATE — Schema validation and rejection codes

The endpoint MUST accept a POST whose body validates against `contract/client-field-report.schema.json` and whose `cohort_token` is accepted, and MUST respond 400 for schema failure, 401 for a bad cohort token, 413 for a body over the size limit and 429 when the nginx per-address rate limit is exceeded.

#### Scenario: schema validation and rejection codes

- **WHEN** a valid report, a report with an extra property, a bad token, a body over the limit and a burst over the rate limit are posted
- **THEN** the responses are 2xx, 400, 401, 413 and 429 respectively and only the first changes any metric

### Requirement: REQ-INGEST-AUTHFIRST — One rate-limit layer and authentication first

The nginx `limit_req` per address MUST be the only rate limit on the route, and the ingest MUST check the cohort token before any other work, so unauthenticated requests cannot use up intake for token holders.

#### Scenario: unauthenticated flood does not starve intake

- **WHEN** 300 requests with a bad cohort token reach the ingest and then a valid report follows
- **THEN** every bad request gets 401 and the valid report gets 202

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

The ingest MUST validate the whole report before it changes any counter, MUST refuse a report that holds a bucket with fewer than 5 attempts (the contract minimum), and MUST drop a bucket under the configured floor (5 or more) from an accepted schema-valid report and count the drop in a metric without identifying labels.

#### Scenario: buckets under 5 attempts are dropped

- **WHEN** a report holds one bucket with 4 attempts and one with 5, and with a configured floor of 10 a report holds one bucket with 7 attempts and one with 10
- **THEN** the first report is refused with 400 and changes no counter, and from the second only the bucket with 10 attempts changes the aggregate while the drop counter grows by one

### Requirement: REQ-INGEST-ALERT — Failure-rate alert by protocol and ASN

The alert rules MUST include a rule that fires when the client failure ratio for a protocol and ASN exceeds the configured threshold over the window with at least the configured attempts, and a promtool test MUST prove the firing and non-firing cases.

#### Scenario: failure-rate alert by protocol and asn

- **WHEN** promtool replays a series with 60 percent failures for one protocol and ASN and one with 5 percent
- **THEN** the first fires and the second does not

### Requirement: REQ-INGEST-POISON-BOUNDS — One report cannot dominate the aggregate

The field reports are unauthenticated client input under one shared cohort token. The ingest MUST add at most `max_attempts_per_report` attempts from one report, scaling a larger report down and counting it, MUST rank asn and country top-N candidates by accepted reports and require `top_n_min_reports` of them, and MUST export accepted reports by protocol and ASN so alerts can require several reports.

#### Scenario: one large report is bounded

- **WHEN** one report holds 4000 attempts with a cap of 1000, and one network sends a single report with 100000 attempts while 20 other networks send three or more small reports
- **THEN** the report adds 1000 attempts in its original proportions and is counted as capped, and only the 20 networks with enough reports receive their own label

### Requirement: REQ-INGEST-SECREVIEW — Security review is recorded

The verification file MUST record the `security-review` skill result for the endpoint covering authentication, abuse limits, input validation, log content and denial of service.

#### Scenario: security review is recorded

- **WHEN** the change enters review
- **THEN** `verification.md` names the review result and each finding is resolved or tracked
