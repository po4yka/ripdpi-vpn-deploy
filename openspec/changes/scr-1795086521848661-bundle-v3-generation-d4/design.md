## Context

`scripts/emit-bundle.sh` produces v2 from secrets and inventory. Liveness quorum and cascade-leg-health outputs exist in `scripts/protocol-liveness.py` and `scripts/check-cascade-leg-health.py`.

## Goals / Non-Goals

- Health in the bundle is derived, bounded and expires.
- Non-goal: the client failover algorithm (R4) and ingest (D2).

## Decisions

- Health is read from artifacts the sentinel already produces, not by probing from the generator. Rejected: probing at emit time, because the generator runs where it has no vantage.
- Assumption: bundle generation runs on the operator machine and reads the latest liveness result file or the control-plane adapter output; the exact source is chosen in the first step.
- Assumption: the cohort token is a SOPS secret `field_report.cohort_token` plus `field_report.previous_cohort_token`, rotated by a new subcommand of `scripts/rotate-secrets.sh`; a new vpnd subcommand is not introduced.
- Assumption: v2 removal is a hard break named in the proposal; no flag keeps v2.

## Contracts and ownership

- `scripts/emit-bundle.sh`, `scripts/validate-bundle.py`, `scripts/rotate-secrets.sh`, secrets schema and coverage scripts, `docs/reference/ripdpi-bundle.md`, `tests/unit/test_emit_bundle_host_selection.py` and new tests. Serialized after D1 on shared contract files.

## Risks / Trade-offs

- Stale health misleads the client -> ttl and unknown-on-stale rules.
- Token leak links reports to a cohort only; rotation limits exposure.
- Hard v2 break strands old app versions -> release R4 first.

## Migration Plan

Forward only. Land after D1 and D3, release the client with bundle v3 support, then regenerate bundles. Rollback is a revert of the generator and the schema together.
