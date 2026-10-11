# XRY-1791617991738391: Deliver selectable alternate XHTTP endpoints and measured typed tuning

## Objective

Deliver selectable alternate XHTTP endpoints and measured typed tuning. All execution checkboxes remain open; this is planning, not implementation or deployment approval.

## Ownership

- scripts/emit-singbox.sh
- scripts/liveness_profiles.py
- scripts/check-singbox-client-compatibility.py
- secrets/schema.json
- scripts/validate-secrets.py
- ansible/roles/xray/templates/config.json.j2
- ansible/roles/xray/defaults/main.yml
- ansible/roles/xray/CLAUDE.md
- ansible/roles/nginx-xhttp/tasks/enable.yml
- ansible/roles/nginx-xhttp/templates/site.conf.j2
- ansible/roles/nginx-xhttp/CLAUDE.md
- docs/CLIENT-NOTES.md
- docs/XRAY-RELEASE-LINE.md
- docs/PQ-REALITY-ADOPTION.md
- tests/unit/test_liveness_profiles.py
- tests/unit/test_relay_fallback.py
- tests/unit/test_secrets_schema.py
- NEW: tests/unit/test_xhttp_alternate_profiles.py
- NEW: tests/integration/xhttp_delivery_matrix/
- NEW: docs/XHTTP-DELIVERY-PROFILES.md
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] XRY-1791618003859679 Deliver primary and alternate endpoint artifacts with exact identity selection and authenticated client regressions #feature @item:XRY-1791617991738391
- [ ] XRY-1791618006858260 Verify exact engine capabilities and implement a small typed mode and tuning allowlist with parser and transfer tests #feature @item:XRY-1791617991738391
- [ ] XRY-1791618007864586 Integrate actual endpoint liveness and comparative delivery fault idle reconnect and resource measurements #feature @item:XRY-1791617991738391
- [ ] XRY-1791618008836301 Run privacy security rollback and full gates and document accepted profiles coordinated client rollout and PQE HOLD #feature @item:XRY-1791617991738391

## Verification

- `mise exec -- python3 -m pytest tests/unit/test_liveness_profiles.py tests/unit/test_relay_fallback.py tests/unit/test_secrets_schema.py`
- `make liveness-profile-check`
- `make snapshot-check`
- `build-gate -- make check`
- `NEW make test-xhttp-delivery-matrix — Prove selectable alternate, exact typed modes, comparative measurements and rollback with owned client/server fixtures.`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Implementation starts only after the canonical portfolio prerequisites are satisfied and separately authorized. Planning alone neither starts work nor checks an execution step.
