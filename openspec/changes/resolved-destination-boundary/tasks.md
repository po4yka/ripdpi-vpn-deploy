# SEC-1791617841911853: Enforce resolved destination isolation for P0 P1 and Hysteria2

## Objective

Enforce resolved destination isolation for P0 P1 and Hysteria2. All execution checkboxes remain open; this is planning, not implementation or deployment approval.

## Ownership

- ansible/roles/xray/templates/config.json.j2
- ansible/roles/xray/tasks/enable.yml
- ansible/roles/xray/CLAUDE.md
- ansible/roles/hysteria/templates/config.yaml.j2
- ansible/roles/hysteria/tasks/enable.yml
- ansible/roles/hysteria/CLAUDE.md
- scripts/validate-secrets.py
- tests/unit/test_secrets_schema.py
- NEW: tests/unit/test_transport_destination_boundary.py
- NEW: tests/integration/transport_destination_boundary/
- NEW: docs/TRANSPORT-DESTINATION-POLICY.md
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] SEC-1791617852155511 Define the resolved destination policy and implement typed Xray and Hysteria2 enforcement with schema and rendering regressions #bug !crit @item:SEC-1791617841911853
- [ ] SEC-1791617853671017 Bind resolution and final dialing and add exact runtime mixed-answer rebinding and retry tests #bug !crit @item:SEC-1791617841911853
- [ ] SEC-1791617861504003 Prove public forwarding trusted plumbing rejection rollback and private diagnostics in owned native integration #bug !crit @item:SEC-1791617841911853
- [ ] SEC-1791617866332021 Review affected snapshots run required local gates and document exact source versus separately authorized staging acceptance #bug !crit @item:SEC-1791617841911853

## Verification

- `mise exec -- python3 -m pytest tests/unit/test_secrets_schema.py tests/unit/test_xray_xhttp_only.py`
- `make snapshot-check`
- `build-gate -- make check`
- `NEW make test-transport-destination-boundary — Run credential-free exact pinned-runtime isolation and positive public forwarding tests in owned namespaces.`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Implementation starts only after the canonical portfolio prerequisites are satisfied and separately authorized. Planning alone neither starts work nor checks an execution step.
