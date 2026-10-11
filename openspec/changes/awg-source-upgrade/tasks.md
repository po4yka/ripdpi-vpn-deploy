# SCR-1791618073850409: Upgrade pinned AmneziaWG sources with unchanged reviewed wire settings

## Objective

Upgrade pinned AmneziaWG sources with unchanged reviewed wire settings. All execution checkboxes remain open; this is planning, not implementation or deployment approval.

## Ownership

- secrets/prod.secrets.example.yaml
- scripts/bootstrap-secrets.sh
- scripts/ci-bootstrap-secrets.sh
- secrets/schema.json
- ansible/roles/amneziawg/tasks/enable.yml
- ansible/roles/amneziawg/templates/awg-quick@.service.j2
- ansible/roles/amneziawg/handlers/main.yml
- ansible/roles/amneziawg/CLAUDE.md
- ansible/roles/runtime-release/tasks/source-build.yml
- scripts/emit-sbom.py
- contract/cohort-fingerprint.golden.json
- contract/amneziawg-arm64-version-floor.json
- scripts/check-amneziawg-arm64-upstream.py
- tests/unit/test_amneziawg_source_pins.py
- tests/unit/test_amneziawg_native_lifecycle.py
- tests/unit/test_transport_p2_lifecycle.py
- tests/unit/test_amneziawg_version_floor.py
- docs/AWG-COHORTS.md
- docs/CLIENT-NOTES.md
- docs/TESTING.md
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] SCR-1791618078367215 Refresh exact source pair provenance toolchain and client compatibility then update pin consumers #feature @item:SCR-1791618073850409
- [ ] SCR-1791618079169597 Deliver real candidate builds and unchanged-wire authenticated interoperability #feature @item:SCR-1791618073850409
- [ ] SCR-1791618080142425 Prove warm pin and unit adoption compensating failures and unrelated tunnel preservation #feature @item:SCR-1791618073850409
- [ ] SCR-1791618081446678 Complete source gates and separately authorized physical and 48-hour staging candidate acceptance #feature @item:SCR-1791618073850409

## Verification

- `mise exec -- python3 -m pytest -q tests/unit/test_amneziawg_source_pins.py tests/unit/test_transport_p2_lifecycle.py tests/unit/test_amneziawg_version_floor.py`
- `make test-native-runtime`
- `make snapshot-check`
- `build-gate -- make check`
- `Existing when the qualified peer checkout is available: make task-federation PEER_ROOT=<RIPDPI-checkout>`
- `NEW build-gate -- make test-awg-source-candidate; implementation must add exact source-pair build interoperability and warm-adoption tests using existing job ceilings`
- `NEW make verify-awg-arm64-candidate; implementation must validate explicit physical candidate evidence without changing the S3/S4 safe floor`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Native `make test-native-runtime` and the dependency-provided native acceptance targets run only on the explicitly isolated Linux root/systemd/TUN host. macOS or missing privileges are prerequisite failures, never silent skips or mocked substitutes.

Implementation starts only after the canonical portfolio prerequisites are satisfied and separately authorized. Planning alone neither starts work nor checks an execution step.
