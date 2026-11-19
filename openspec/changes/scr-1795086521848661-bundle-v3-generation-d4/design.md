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

## Implementation decisions

- Health source (first step): the operator names a JSON health configuration in `BUNDLE_HEALTH_FILE` that points at the protocol-liveness result (`last-evidence.json`), maps each bundle host to its liveness policy id, and may name a cascade leg health record per host. `scripts/bundle_health.py` derives the status; `scripts/client_payload.py` calls it only for `--bundle` with that file.
- Without `BUNDLE_HEALTH_FILE` the generator omits `ripdpi.endpoints`. Subscription delivery, device lifecycle and drift checks materialize the same bundle without it, and a generation-time `observed_at` would make every drift check report a change. `unknown` covers absent, stale or unmapped input when the file is given.
- The cohort token rotation is `scripts/rotate-cohort-token.sh`, not a subcommand of `scripts/rotate-secrets.sh`: `scripts/CLAUDE.md` keeps one job per script. It reuses that script's writer lock, killed-run backup contract and audit record, and writes through `sops set --value-stdin`, so no token reaches argv, the environment or output. A real sops 3.13.3 run against a throwaway age key generated, then twice rotated a token, kept unrelated keys and printed no token.
- One previous token is kept: a rotation replaces any older previous token, so a token is accepted for at most one overlap (`OVERLAP_DAYS`, 1 to 30, default 7) after it is replaced.
- The SOPS key `field_report` holds both the client fields (`enabled`, `endpoint`, `max_reports_per_day`) and the ingest tokens; the bundle carries only the current token.
- The v2 emission path was already removed by D1 (`113ae3aa`); this change adds the test that a generated bundle is v3 and validates.
