# MON-1791618056169855: Deliver topology-aware authenticated transport health and secure smoke probes

## Objective

Deliver topology-aware authenticated transport health and secure smoke probes. All execution checkboxes remain open; this is planning, not implementation or deployment approval.

## Ownership

- ansible/playbooks/verify.yml
- ansible/playbooks/smoke-test.yml
- ansible/playbooks/os-maintenance.yml
- ansible/roles/watchdog/templates/vpn-watchdog.env.j2
- ansible/roles/watchdog/templates/vpn-watchdog.sh.j2
- ansible/roles/watchdog/CLAUDE.md
- ansible/templates/listener-manifest.json.j2
- scripts/liveness_profiles.py
- scripts/protocol-liveness.py
- scripts/check-liveness-profile-compatibility.py
- tests/unit/test_watchdog_templates.py
- tests/unit/test_watchdog_protocol_probe.py
- tests/unit/test_smoke_test_cleanup.py
- tests/unit/test_runtime_audit_regressions.py
- tests/unit/test_protocol_liveness_sentinel.py
- docs/TESTING.md
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] MON-1791618060162436 Implement effective topology resolution across verify watchdog and secure smoke clients #feature !high @item:MON-1791618056169855
- [ ] MON-1791618061120158 Deliver authenticated bounded checks and exact recovery targeting with private results #feature !high @item:MON-1791618056169855
- [ ] MON-1791618061966295 Exercise warm runtime adoption real hopping and per-surface outage and credential failures #feature !high @item:MON-1791618056169855
- [ ] MON-1791618062766877 Integrate truthful evidence and preserved lifecycle regressions then complete source gates #feature !high @item:MON-1791618056169855

## Verification

- `mise exec -- python3 -m pytest -q tests/unit/test_watchdog_templates.py tests/unit/test_watchdog_protocol_probe.py tests/unit/test_smoke_test_cleanup.py tests/unit/test_runtime_audit_regressions.py`
- `make test-native-runtime`
- `make snapshot-check`
- `build-gate -- make check`
- `NEW make test-topology-authenticated-probes; implementation must add exact-client topology outage secure smoke warm-adoption and hopping cases to the native lane`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Native `make test-native-runtime` and the dependency-provided native acceptance targets run only on the explicitly isolated Linux root/systemd/TUN host. macOS or missing privileges are prerequisite failures, never silent skips or mocked substitutes.

Implementation starts only after the canonical portfolio prerequisites are satisfied and separately authorized. Planning alone neither starts work nor checks an execution step.
