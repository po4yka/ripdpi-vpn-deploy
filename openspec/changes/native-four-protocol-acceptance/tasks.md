## Local completion scope (2026-10-16)

The owner authorizes full local implementation and removes staging soak, external recipient, Android emulator and physical-device acceptance from this change. Completion requires actual pinned local engines, isolated Linux systemd/network namespaces/TUN where applicable, authenticated positive and rejection traffic, compensation, privacy and complete source checks. Synthetic credentials are test inputs; mocks, render-only checks and refusal-only results cannot replace runnable behavior. External devices, provider actions, production rollout and promotion are outside acceptance. Earlier observations below retain their original source and limitations; removed external gates are excluded by this scope revision, never recorded as passed.

# TST-1791618356595983: Deliver isolated native acceptance for every baseline transport

## Objective

Deliver isolated native acceptance for every baseline transport. Local implementation is authorized; checkboxes require observed local behavior and source gates.

## Ownership

- tests/unit/test_protocol_liveness.py
- tests/unit/test_liveness_profiles.py
- tests/unit/test_amneziawg_native_lifecycle.py
- tests/unit/test_nginx_transaction_native.py
- tests/unit/test_monitoring_logrotate.py
- ansible/molecule/full-stack/
- docs/TESTING.md
- Makefile
- Canonical Make runner composing the existing native fixtures and complete named suites
- Existing isolated native CI lane extended through its current selector
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] TST-1791618369402905 Deliver exact-engine Linux four-protocol positive and rejection cases through existing adapters #feature !high @item:TST-1791618356595983
- [ ] TST-1791618370981853 Exercise warm activation retirement rotation and failed authority compensation with real processes #feature !high @item:TST-1791618356595983
- [ ] TST-1791618372464891 Prove both-family firewall-owned hopping and isolated unrelated-UDP preservation #feature !high @item:TST-1791618356595983
- [ ] TST-1791618373730661 Wire complete no-skip native acceptance into source checks with exact redacted evidence and cleanup #feature !high @item:TST-1791618356595983

## Verification

- `mise exec -- python3 -m pytest -q tests/unit/test_protocol_liveness.py tests/unit/test_liveness_profiles.py tests/unit/test_amneziawg_native_lifecycle.py tests/unit/test_nginx_transaction_native.py tests/unit/test_monitoring_logrotate.py`
- `NEW make transport-native-acceptance on the explicitly isolated Linux runner; all cases complete with zero skips and authenticated evidence`
- `build-gate -- make check`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Local implementation is authorized. Acceptance follows the dependency graph; only observed checks complete execution steps.
