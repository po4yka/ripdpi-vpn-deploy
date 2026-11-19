## Purpose

Define one tested retention contract for observability data classes and a receipt that proves Telegram alert delivery.

## ADDED Requirements

### Requirement: REQ-RET-TABLE — Retention table is complete

The operations reference MUST list a finite retention for Prometheus, the vmagent queue, service logs, journal, and field-report data, and a check MUST fail when a data class has no value or an unbounded value.

#### Scenario: retention table is complete

- **WHEN** a data class row is removed or set to unlimited
- **THEN** the retention check fails

### Requirement: REQ-RET-ENFORCED — Rendered configuration matches the table

The rendered Prometheus, vmagent and journald configuration MUST carry the documented values.

#### Scenario: rendered configuration matches the table

- **WHEN** the templates are rendered with default variables
- **THEN** the rendered flags equal the table values and the snapshot test passes

### Requirement: REQ-RET-FIELDREPORT — No raw field-report retention

The ingest MUST NOT retain a raw report after aggregation, and the retention table MUST state raw retention as none.

#### Scenario: no raw field-report retention

- **WHEN** a report is ingested and the state and log directories are listed
- **THEN** no raw report exists

### Requirement: REQ-DELIVERY-RECEIPT — Telegram delivery receipt

After explicit operator authorization, the system MUST send a test alert through Alertmanager and the Telegram relay and MUST record a receipt with the alert name, UTC time and the Telegram message id and MUST NOT record the bot token or chat id.

#### Scenario: telegram delivery receipt

- **WHEN** the operator authorizes the staging drill and the test alert is sent
- **THEN** the receipt validates against its schema and a search of the receipt finds no token or chat id
