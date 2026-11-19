# Change: Enforce observability retention and prove Telegram alert delivery

Task ID: `MON-1795086847564764`

## Why

Collector retention and the vmagent queue are bounded by the existing resource-bounded-observability spec, but there is no single documented and tested retention contract for logs and the new field-report data, and alert delivery to Telegram has not been proven with a receipt. Part of epic `EPC-1795085241910080`.

## What Changes

- Overlap, narrowed: `resource-bounded-observability` (spec, done as `MON-1792080593038468`) already enforces collector and queue limits; this change adds only the retention table, log retention checks and the field-report data class and does not change those limits.
- Overlap, narrowed: `MON-1794126016474351` (Telegram alert messages, doing) owns message content and says real delivery needs separate authorization; this change owns only the delivery receipt and does not touch message rendering. If that task lands first, the receipt reuses its message; otherwise the receipt uses the current format.
- `ops-1792927264049641` (HTTPS renewal) was checked and is unrelated.
- Counterpart RIPDPI work: none.

## Capabilities

### New Capabilities

- `operations/observability-retention-delivery`: retention contract and delivery receipt.

### Modified Capabilities

- None.

## Impact

- Docs: `docs/reference/observability-operations.md`.
- Ansible: `ansible/roles/observability_control_plane/`, `ansible/roles/observability_agent/` templates for retention flags.
- Evidence: delivery receipt format under `contract/observability-evidence.schema.json`.
