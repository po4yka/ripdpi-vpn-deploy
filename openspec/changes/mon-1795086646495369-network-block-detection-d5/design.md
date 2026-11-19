## Context

Client failure ratios come from D2 metrics; sentinel success comes from D3 metrics. `fleet-health-rotation` and `scripts/fleet-rotate.sh` own rotation.

## Goals / Non-Goals

- Distinguish network blocks from server failures with explicit alert logic.
- Non-goal: automatic rotation, or ASN-level user attribution.

## Decisions

- Pure PromQL join on protocol with ASN as the client-side dimension. Rejected: a new detector service.
- Assumption: thresholds, window and attempts floor are role variables with conservative defaults and are tuned after D7.
- Assumption: the rotation hint is text in the alert annotation plus a read-only helper output in fleet-rotate PLAN that queries current active alerts; if the query surface is not available the hint is shown from a local file the operator exports. Decided in step 3.
- Assumption: carrier or ISP names are not used in labels or docs (repo policy); ASN numbers and country codes only.

## Contracts and ownership

- `observability-alert-rules.yml.j2` and test template (serialized lane with D2, D3, D6), `scripts/fleet-rotate.sh`, `docs/reference/observability-operations.md`.

## Risks / Trade-offs

- Poisoned reports raise false blocks -> attempts floor, sentinel-healthy condition and operator decision.
- Alert noise -> duration threshold and low-sample suppression.

## Migration Plan

Forward only; the rule ships with thresholds that favour silence. Rollback removes the rule.
