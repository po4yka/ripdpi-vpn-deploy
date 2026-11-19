## Purpose

Define how the bundle generator derives endpoint health from server-side liveness data and emits the field-report configuration and rotating cohort token in bundle v3.

## ADDED Requirements

### Requirement: REQ-GEN-V3 — Generator emits v3 only

The generator MUST emit a bundle that validates against the v3 schema and MUST NOT emit `schema_version` 2.

#### Scenario: generator emits v3 only

- **WHEN** the generator runs against the golden fixture inputs
- **THEN** the output validates with `scripts/validate-bundle.py` as v3 and the old v2 path is removed

### Requirement: REQ-GEN-HEALTH — Health from quorum

For each endpoint the generator MUST set `health.status` from the protocol-liveness quorum and cascade-leg-health, MUST set `observed_at` to the input timestamp, and MUST set `unknown` when input is absent or older than a configured maximum age.

#### Scenario: health from quorum

- **WHEN** liveness input marks an endpoint down, another healthy, a third has no input
- **THEN** the bundle has down, healthy and unknown respectively

### Requirement: REQ-GEN-TTL — Health time-to-live

The generator MUST set `ttl_seconds` from configuration and MUST NOT exceed the configured maximum.

#### Scenario: health time-to-live

- **WHEN** configuration requests a ttl above the maximum
- **THEN** generation fails with a clear error

### Requirement: REQ-GEN-FIELDREPORT — Field-report block from configuration

The generator MUST emit `field_report` with `endpoint` as an https URL, `cohort_token` and `max_reports_per_day` from configuration and MUST omit the block when the operator has not enabled field reports.

#### Scenario: field-report block from configuration

- **WHEN** field reports are disabled in configuration
- **THEN** the bundle has no `field_report` and still validates

### Requirement: REQ-GEN-COHORT-ROTATE — Cohort token rotation

The token MUST be shared per cohort and MUST NOT derive from a device identity. A rotation command MUST generate a new token, publish it in new bundles and keep the previous token accepted by ingest for a bounded overlap, and the token MUST NOT be printed in logs or Ansible output.

#### Scenario: cohort token rotation

- **WHEN** the operator rotates the cohort token
- **THEN** new bundles carry the new token, the ingest accepts both during the overlap and the old token is rejected after it, and the logs contain neither

#### Scenario: second rotation inside the overlap

- **WHEN** the operator rotates again while the previous token is still accepted
- **THEN** the command refuses and changes nothing unless `FORCE=1` states the cut-off of devices that hold the older token
