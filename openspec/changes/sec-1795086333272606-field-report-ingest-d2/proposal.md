# Change: Ingest opt-in client field reports into bounded Prometheus metrics

Task ID: `SEC-1795086333272606`

## Why

Client-path health is unknown. Once D1 defines the report, the server needs an internet-facing endpoint that turns reports into metrics without becoming a tracking system. Part of epic `EPC-1795085241910080`; blocked by D1 (`SCR-1795085709140075`).

## What Changes

- New POST endpoint on the subscription host with schema validation, `cohort_token` check, rate limit and body size limit.
- Aggregation into Prometheus metrics with bounded labels, and failure-rate alerts by protocol and ASN in `observability-alert-rules.yml.j2`.
- Request logging keeps the existing categorical policy; no IP is logged beyond it.
- Counterpart RIPDPI work: R3 (opt-in report client) sends the reports; R2 vendors the contract.
- Security review per the repository `security-review` skill is part of acceptance.

## Capabilities

### New Capabilities

- `operations/field-report-ingest`: ingest endpoint, limits, metrics and alerts.

### Modified Capabilities

- None.

## Impact

- Ansible: `ansible/roles/subscription-host/` (endpoint, nginx), `ansible/roles/observability_control_plane/templates/observability-alert-rules.yml.j2` and `observability-alert-rules.test.yml.j2`.
- Contracts: `contract/observability-metric-manifest.example.json` gains the new metrics; reads `contract/client-field-report.schema.json`.
- Secrets: cohort token comes from SOPS via D4; no new plaintext secret.
