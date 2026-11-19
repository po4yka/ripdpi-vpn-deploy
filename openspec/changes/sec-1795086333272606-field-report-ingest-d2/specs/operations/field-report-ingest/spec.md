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

The aggregation MUST expose counters and a histogram with only the labels protocol, failure_stage, network, country and server_ref; `network` MUST be `<mcc>-<mnc>` for a `sim` report and `as<asn>` for a `server_hint` report when that value is one of the configured top-N values, else "other", and "unknown" for a `none` report; `server_ref` MUST be accepted only if it is in the current bundle endpoint list, else "other".

#### Scenario: bounded metric labels

- **WHEN** reports arrive for 1000 distinct ASNs and unknown `server_ref` values, and `sim`, `server_hint` and `none` reports arrive with top-N bounds of 1
- **THEN** the exported series count stays at or below the configured bound, and one operator, one ASN, "other" and "unknown" are the only network labels

### Requirement: REQ-INGEST-MINATTEMPT — Buckets under 5 attempts are dropped

The ingest MUST validate the whole report before it changes any counter, MUST refuse a report that holds a bucket with fewer than 5 attempts (the contract minimum), and MUST drop a bucket under the configured floor (5 or more) from an accepted schema-valid report and count the drop in a metric without identifying labels.

#### Scenario: buckets under 5 attempts are dropped

- **WHEN** a report holds one bucket with 4 attempts and one with 5, and with a configured floor of 10 a report holds one bucket with 7 attempts and one with 10
- **THEN** the first report is refused with 400 and changes no counter, and from the second only the bucket with 10 attempts changes the aggregate while the drop counter grows by one

### Requirement: REQ-INGEST-ALERT — Failure-rate alert by protocol and network

The alert rules MUST include a rule that fires when the client failure ratio for a protocol and network (a SIM operator or an ASN) exceeds the configured threshold over the window with at least the configured attempts, and a promtool test MUST prove the firing and non-firing cases.

#### Scenario: failure-rate alert by protocol and network

- **WHEN** promtool replays 60 percent failures for one protocol and ASN, 70 percent for one protocol and SIM operator, and 5 percent for another protocol in that operator
- **THEN** the first two fire and the third does not

### Requirement: REQ-INGEST-POISON-BOUNDS — One report cannot dominate the aggregate

The field reports are unauthenticated client input under one shared cohort token. The ingest MUST add at most `max_attempts_per_report` attempts from one report, scaling a larger report down and counting it, MUST rank operator, ASN and country top-N candidates by accepted reports, with operators and ASNs in separate rankings, and require `top_n_min_reports` of them, and MUST export accepted reports by protocol and network so alerts can require several reports.

#### Scenario: one large report is bounded

- **WHEN** one report holds 4000 attempts with a cap of 1000, and one network sends a single report with 100000 attempts while 20 other networks send three or more small reports
- **THEN** the report adds 1000 attempts in its original proportions and is counted as capped, and only the 20 networks with enough reports receive their own label

### Requirement: REQ-HINT-RESPONSE — Network hint answer

The ingest MUST answer `GET` on the network-hint path, after the same cohort-token check as the report route, with 200 and a body that validates against `contract/client-network-hint.schema.json`, 204 with no body when the address has no routed ASN and country, 401 for a bad token and 404 when the hint is off. The hint MUST NOT change a report counter.

#### Scenario: network hint answer

- **WHEN** hints are requested for an address in a routed range, an IPv6 and an IPv4-mapped address, a not-routed, country-less, unknown or malformed address, a bad or missing token, and with the hint off
- **THEN** the answers are 200 with a valid hint, 204, 401 and 404 respectively and the metrics are unchanged

### Requirement: REQ-HINT-PEER — Only the TCP peer address is looked up and none is kept

nginx MUST pass the TCP peer address in its own header, MUST NOT pass a forwarding header and MUST refuse with 400 a request that carries `X-Forwarded-For`, `Forwarded`, `X-Real-IP` or the peer header, under its own per-address `limit_req` zone. The ingest MUST NOT write the address to a response, log, metric or file.

#### Scenario: only the tcp peer address is looked up and none is kept

- **WHEN** the vhost is rendered with the hint on, and hints are served and the service output and state are searched for the requested addresses
- **THEN** the location sets the peer header from `$remote_addr`, clears the forwarding headers, refuses their presence and has no `real_ip` directive, and no address is found

### Requirement: REQ-HINT-DATASET — Pinned offline dataset

The IP-to-ASN dataset MUST carry a license compatible with the repository, recorded in a third-party notice, and MUST be pinned by version and SHA-256. Deploy MUST copy only the controller file matching the pin and never fetch the dataset. An operator script MUST refresh it, pin only a file the ingest loads and never replace a stored pinned copy.

#### Scenario: pinned offline dataset

- **WHEN** the refresh script receives a good download, a second build of the same version and an overlapping download
- **THEN** the good download is stored with its printed pin, the second build is refused without changing it, and the bad one is refused

### Requirement: REQ-HINT-DATASET-FAILURE — A bad dataset turns off only the hint

The ingest MUST verify the SHA-256 at start, MUST read the dataset with a bounded line length and a decompressed size cap, and MUST refuse a malformed, overlapping or truncated dataset. After a refusal it MUST keep the report route running without the hint route, with a categorical log line and `vpn_field_report_network_hint_available 0`.

#### Scenario: a bad dataset turns off only the hint

- **WHEN** the service starts with a pin mismatch, an overlapping range, a non-numeric AS, a reversed range, a short line, no IPv4 range, a truncated gzip, a gzip bomb line or a stream over the size cap
- **THEN** the hint route answers 404, the gauge is 0, a valid report is still accepted, the log line is categorical and the gzip bomb stays under the unit memory limit

### Requirement: REQ-INGEST-SECREVIEW — Security review is recorded

The verification file MUST record the `security-review` skill result for the endpoint covering authentication, abuse limits, input validation, log content and denial of service.

#### Scenario: security review is recorded

- **WHEN** the change enters review
- **THEN** `verification.md` names the review result and each finding is resolved or tracked
