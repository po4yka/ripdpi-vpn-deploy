# ANS-1791617913525586: Commit transport runtimes only after complete configuration and readiness acceptance

## Objective

Commit transport runtimes only after complete configuration and readiness acceptance. All execution checkboxes remain open; this is planning, not implementation or deployment approval.

## Ownership

- ansible/roles/runtime-release/tasks/main.yml
- ansible/roles/runtime-release/files/runtime_release_activate.py
- ansible/roles/runtime-release/CLAUDE.md
- ansible/roles/xray-runtime/tasks/main.yml
- ansible/roles/xray-runtime/CLAUDE.md
- ansible/roles/xray/tasks/enable.yml
- ansible/roles/xray/handlers/main.yml
- ansible/roles/xray/CLAUDE.md
- ansible/roles/hysteria/tasks/enable.yml
- ansible/roles/hysteria/handlers/main.yml
- ansible/roles/hysteria/CLAUDE.md
- tests/unit/test_runtime_release_contract.py
- tests/unit/test_runtime_release_consumers.py
- tests/unit/test_hysteria_runtime_release.py
- NEW: tests/unit/test_transport_runtime_acceptance.py
- NEW: tests/integration/transport_runtime_acceptance/
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] ANS-1791617918944560 Add staged consumer acceptance and bounded recovery contracts to the existing runtime foundation with unit failure tests #bug !high @item:ANS-1791617913525586
- [ ] ANS-1791617919627692 Adopt complete candidate validation and acceptance in Xray and Hysteria2 with actual role normal and check-mode regressions #bug !high @item:ANS-1791617913525586
- [ ] ANS-1791617921061642 Prove native positive adoption failure compensation process-death recovery and unchanged retry across both transports #bug !high @item:ANS-1791617913525586
- [ ] ANS-1791617922800117 Review authority boundaries run focused and full gates and record exact source readiness without live claims #bug !high @item:ANS-1791617913525586

## Verification

- `mise exec -- python3 -m pytest tests/unit/test_runtime_release_contract.py tests/unit/test_runtime_release_consumers.py tests/unit/test_hysteria_runtime_release.py tests/unit/test_xray_xhttp_only.py`
- `make snapshot-check`
- `build-gate -- make check`
- `NEW make test-transport-runtime-acceptance — Exercise exact owned native upgrade and rollback acceptance plus process-death recovery without real inventory.`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Implementation starts only after the canonical portfolio prerequisites are satisfied and separately authorized. Planning alone neither starts work nor checks an execution step.
