# Change: Define client field-report v1 and ripdpi-bundle v3 contracts

Task ID: `SCR-1795085709140075`

## Why

The app sends nothing to the server and the only client contract is `contract/ripdpi-bundle.schema.json` v2, so client-path health is unknown (`docs/reference/protocol-liveness.md`). The owner decided on opt-in, anonymous, aggregated client field reports. Both repositories need one canonical contract before ingest (D2), generation (D4) or client code can start. Part of epic `EPC-1795085241910080`.

## What Changes

- New `contract/client-field-report.schema.json` v1 (window, client, network, buckets).
- BREAKING: `contract/ripdpi-bundle.schema.json` moves to `schema_version` const 3 and replaces v2. A v2 bundle is rejected; there is no compatibility shim. Per endpoint `health` and a top-level `field_report` object are added.
- Golden and negative fixtures under `contract/` and `contract/negative/`; validator coverage in `scripts/validate-bundle.py` and `tests/unit/test_bundle_schema.py`.
- Counterpart RIPDPI changes: R2 vendors these contracts and the failure-stage taxonomy; R3 emits reports; R4 consumes bundle v3 health in failover; R1 removes embedded secrets from app assets.

## Capabilities

### New Capabilities

- `clients/field-report-contract`: client-field-report v1 and bundle v3 wire contract.

### Modified Capabilities

- None. The existing v2 bundle contract is replaced by an ADDED requirement set; the v2 spec text in `docs/reference/ripdpi-bundle.md` is rewritten.

## Impact

- Contracts: `contract/client-field-report.schema.json`, `contract/ripdpi-bundle.schema.json`, `contract/ripdpi-bundle.example.json`, `contract/ripdpi-bundle.golden-full.json`, `contract/negative/`.
- Scripts and docs: `scripts/validate-bundle.py`, `docs/reference/ripdpi-bundle.md`, `AGENTS.md` source-of-truth table row.
- Cross-repository: RIPDPI R2 vendored copy. Blocks D2 and D4.
