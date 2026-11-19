## Purpose

Define the end-to-end acceptance that proves the field analytics chain works with a real client against a staging node with one protocol blocked.

## ADDED Requirements

### Requirement: REQ-E2E-CLASSIFY — App classifies the stage

When one protocol is blocked on the staging node with DROP the app MUST report failure with the stage tcp_connect, tls_handshake, quic_handshake or idle_timeout as the taxonomy requires for that protocol, and with RST MUST report tcp_reset.

#### Scenario: app classifies the stage

- **WHEN** nftables DROP and then RST rules block one protocol on the staging node and the client attempts connections
- **THEN** the exported report buckets carry the expected failure_stage for each case

### Requirement: REQ-E2E-INGEST — Report reaches ingest

The report MUST be ingested and appear in the field-report metrics with the correct protocol, failure_stage and server_ref and no identifying data.

#### Scenario: report reaches ingest

- **WHEN** the client reaches its hourly reporting point or the test forces a flush
- **THEN** the staging Prometheus shows the series and a search for the device address finds none in logs

### Requirement: REQ-E2E-ALERT — Alert fires

The block-detection alert MUST fire for the test ASN and protocol while the sentinel reports healthy.

#### Scenario: alert fires

- **WHEN** the failure ratio exceeds the threshold with enough attempts
- **THEN** the alert is active in Alertmanager and the staging Telegram receives it if delivery is authorized

### Requirement: REQ-E2E-BUNDLE — Bundle marks degraded

A regenerated bundle MUST show the blocked endpoint with `health.status` degraded or down and a valid `observed_at` and `ttl_seconds`.

#### Scenario: bundle marks degraded

- **WHEN** the generator runs after the sentinel marks the endpoint failing, or the operator injects the quorum input
- **THEN** the bundle validates as v3 and shows the status

### Requirement: REQ-E2E-FAILOVER — Client fails over and recovers

The client MUST move to another healthy endpoint within the configured time and MUST return to the original after the block is removed and health expires or turns healthy.

#### Scenario: client fails over and recovers

- **WHEN** the client loads the degraded bundle during the block, then the block is removed
- **THEN** traffic uses another protocol during the block and the original afterwards
