# SCR-1791618039091425: Deliver authoritative AmneziaWG device enrollment and client bindings

## Objective

Deliver authoritative AmneziaWG device enrollment and client bindings. All execution checkboxes remain open; this is planning, not implementation or deployment approval.

## Ownership

- scripts/new-client.sh
- scripts/rotate-secrets.sh
- scripts/emit-awg.sh
- scripts/emit-bundle.sh
- scripts/liveness_profiles.py
- scripts/validate-secrets.py
- secrets/schema.json
- secrets/prod.secrets.example.yaml
- ansible/roles/amneziawg/tasks/instances.yml
- scripts/ripdpi_cohort_fingerprint.py
- contract/cohort-fingerprint.golden.json
- contract/ripdpi-bundle.schema.json
- tests/unit/test_emit_bundle_host_selection.py
- tests/unit/test_bootstrap_awg_handoff.py
- tests/unit/test_secrets_schema.py
- docs/AWG-COHORTS.md
- docs/RIPDPI-BUNDLE.md
- scripts/CLAUDE.md
- ansible/roles/amneziawg/CLAUDE.md
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] SCR-1791618044456243 Implement the canonical effective AWG binding and coherent schema and caller migration #feature !high @item:SCR-1791618039091425
- [ ] SCR-1791618045140064 Deliver selected-instance pool enrollment and revocation with encrypted transaction regressions #feature !high @item:SCR-1791618039091425
- [ ] SCR-1791618045793096 Emit and resolve exact bound configurations across standalone bundle and liveness consumers #feature !high @item:SCR-1791618039091425
- [ ] SCR-1791618046582572 Prove authenticated two-instance traffic and failure preservation then complete source review gates #feature !high @item:SCR-1791618039091425

## Verification

- `mise exec -- python3 -m pytest -q tests/unit/test_emit_bundle_host_selection.py tests/unit/test_bootstrap_awg_handoff.py tests/unit/test_secrets_schema.py`
- `make snapshot-check`
- `make task-check`
- `build-gate -- make check`
- `Existing when the qualified peer checkout is available: make task-federation PEER_ROOT=<RIPDPI-checkout>`
- `NEW make test-awg-device-binding-runtime; implementation must add exact-binary two-instance Linux TUN enrollment export and revocation coverage to the canonical native lane`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Implementation starts only after the canonical portfolio prerequisites are satisfied and separately authorized. Planning alone neither starts work nor checks an execution step.
