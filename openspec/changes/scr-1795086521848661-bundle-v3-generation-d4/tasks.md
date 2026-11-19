# SCR-1795086521848661: Generate ripdpi-bundle v3 with endpoint health and field-report config

## Objective

`scripts/emit-bundle.sh` emits ripdpi-bundle v3 with per-endpoint health derived from protocol-liveness quorum and cascade-leg-health, a `field_report` block, and a cohort token with a defined rotation.

## Ownership

One writer owns `scripts/emit-bundle.sh`, rotation script changes, secrets schema entries and the new tests. Serialized lane: runs after D1 and D3 land.

## Execution

- [x] SCR-1795086544436996 Rewrite the emission in scripts/emit-bundle.sh to schema_version 3 and remove the v2 path #feature !high @item:SCR-1795086521848661
- [x] SCR-1795086565223483 Derive per-endpoint health and ttl_seconds from protocol-liveness quorum and cascade-leg-health with unknown on absent or stale input #feature !high @item:SCR-1795086521848661
- [x] SCR-1795086581871015 Add the field_report configuration, the cohort token and previous-token secrets entries to secrets/schema.json, secrets/prod.secrets.example.yaml and the coverage scripts #feature !high @item:SCR-1795086521848661
- [x] SCR-1795086600479731 Add the cohort token rotation command to scripts/rotate-secrets.sh without printing the token #feature !high @item:SCR-1795086521848661
- [x] SCR-1795086620548947 Add tests in tests/unit/ for v3 validity, health mapping, stale handling, disabled field reports and rotation overlap #feature !high @item:SCR-1795086521848661

## Verification

Local: `python3 -m pytest tests/unit/test_bundle_schema.py tests/unit/test_emit_bundle_host_selection.py` plus the new tests, `make shellcheck`, `make snapshot-check`, then `make check`. Remote CI. Dry-run: rotation dry-run after authorization. Client: RIPDPI R4 consumes a generated v3 bundle. Artifact: a generated example bundle at the verified SHA.
