# Change: Generate ripdpi-bundle v3 with endpoint health and field-report config

Task ID: `SCR-1795086521848661`

## Why

D1 defines bundle v3. The generator must publish server-observed health so the client can prefer healthy endpoints, and must hand the client the field-report endpoint and a cohort token. Part of epic `EPC-1795085241910080`; blocked by D1 (`SCR-1795085709140075`) and D3 (`MON-1795086175387484`).

## What Changes

- BREAKING: `scripts/emit-bundle.sh` stops emitting v2 and emits v3 only; clients on v2 must update (RIPDPI R4 consumes v3).
- Per-endpoint `health` from the protocol-liveness quorum (`scripts/protocol-liveness.py`) and `scripts/check-cascade-leg-health.py` output; `field_report` block from configuration.
- Cohort token generation and rotation through the secrets tooling, one token per cohort.
- Counterpart RIPDPI work: R4 uses endpoint health in failover; R3 reads `field_report`; R1 ensures no secret is embedded in app assets.

## Capabilities

### New Capabilities

- `clients/bundle-v3-generation`: v3 emission, health derivation and cohort token rotation.

### Modified Capabilities

- None.

## Impact

- Scripts: `scripts/emit-bundle.sh`, `scripts/validate-bundle.py`, `scripts/rotate-secrets.sh`.
- Secrets schema: `secrets/schema.json`, `scripts/validate-secrets.py`, `scripts/check-secrets-coverage.py`, `secrets/prod.secrets.example.yaml` (new cohort token entries).
- Docs: `docs/reference/ripdpi-bundle.md`.
- Cross-repository: RIPDPI R3 and R4.
