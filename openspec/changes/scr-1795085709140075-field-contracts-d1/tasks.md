# SCR-1795085709140075: Define client field-report v1 and ripdpi-bundle v3 contracts

## Objective

This repository is the canonical source of the client-field-report v1 schema and the ripdpi-bundle v3 schema, with golden and negative fixtures and validator coverage. Bundle v3 replaces v2.

## Ownership

One writer owns `contract/client-field-report*`, `contract/ripdpi-bundle*`, `contract/negative/`, `scripts/validate-bundle.py`, `tests/unit/test_bundle_schema.py`, `docs/reference/ripdpi-bundle.md`. Serialized lane before D4.

## Execution

- [x] SCR-1795085965580974 Add contract/client-field-report.schema.json v1 with golden fixture contract/client-field-report.golden.json #feature !high @item:SCR-1795085709140075
- [x] SCR-1795085995858987 Add negative fixtures under contract/negative/ for extra properties, bad failure_stage pairing, forbidden identifiers, fine timestamps and attempts below 5 #feature !high @item:SCR-1795085709140075
- [x] SCR-1795086029049140 Move contract/ripdpi-bundle.schema.json to schema_version 3 with endpoint health and top-level field_report, and update the example and golden bundles #feature !high @item:SCR-1795085709140075
- [x] SCR-1795086060772476 Extend scripts/validate-bundle.py and tests/unit/test_bundle_schema.py to cover the report schema, v2 rejection and expired-health fixture #feature !high @item:SCR-1795085709140075
- [x] SCR-1795086089853517 Rewrite docs/reference/ripdpi-bundle.md for v3, name the v2 break and update the AGENTS.md source-of-truth row #feature !high @item:SCR-1795085709140075
- [x] SCR-1795103564806941 Add required network.source with SIM operator and server-hint rules to client-field-report v1, the client-network-hint v1 contract, bundle field_report.network_hint_endpoint, fixtures and docs #feature !high @item:SCR-1795085709140075

## Verification

Local: `python3 -m pytest tests/unit/test_bundle_schema.py`, `make snapshot-check`, `make docs-check`, then `make check`. Remote CI on the pull request. Client: RIPDPI R2 vendors the fixtures and passes them. Artifact: the schema files at the verified SHA.
