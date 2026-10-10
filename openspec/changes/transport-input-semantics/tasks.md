# SCT-1791617687019287: Reject incoherent transport inputs before runtime mutation

## Objective

Reject incoherent transport inputs before runtime mutation. All execution checkboxes remain open; this is planning, not implementation or deployment approval.

## Ownership

- secrets/schema.json
- secrets/prod.secrets.example.yaml
- scripts/validate-secrets.py
- scripts/spot-check-secrets.py
- scripts/check-secrets-coverage.py
- ansible/roles/runtime-release/files/validate_yaml_mapping.py
- tests/unit/test_secrets_schema.py
- tests/unit/test_spot_check_secrets.py
- tests/unit/test_transport_config_lifecycle.py
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] SCT-1791617711124536 Enforce complete cohort and supported masquerade contracts with accepted-render and early-refusal tests #bug !high @item:SCT-1791617687019287
- [ ] SCT-1791617712074772 Share effective AWG relationship validation with enrollment emitter and native-parser boundaries #bug !high @item:SCT-1791617687019287
- [ ] SCT-1791617713075181 Preserve floor privacy and complete schema coverage snapshots and source gates #bug !high @item:SCT-1791617687019287

## Verification

- `mise exec -- python3 -m pytest -q tests/unit/test_secrets_schema.py tests/unit/test_spot_check_secrets.py tests/unit/test_transport_config_lifecycle.py tests/unit/test_amneziawg_version_floor.py`
- `mise exec -- python3 scripts/check-secrets-coverage.py`
- `build-gate -- make check`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Implementation starts only after the canonical portfolio prerequisites are satisfied and separately authorized. Planning alone neither starts work nor checks an execution step.
