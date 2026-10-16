## Local completion scope (2026-10-16)

The owner authorizes full local implementation and removes staging soak, external recipient, Android emulator and physical-device acceptance from this change. Completion requires actual pinned local engines, isolated Linux systemd/network namespaces/TUN where applicable, authenticated positive and rejection traffic, compensation, privacy and complete source checks. Synthetic credentials are test inputs; mocks, render-only checks and refusal-only results cannot replace runnable behavior. External devices, provider actions, production rollout and promotion are outside acceptance. Earlier observations below retain their original source and limitations; removed external gates are excluded by this scope revision, never recorded as passed.

# ANS-1791618083683925: Deliver coordinated Hysteria ECH server and recipient profiles

## Objective

Deliver coordinated Hysteria ECH server and recipient profiles. Source implementation and PR preparation are authorized. Execution steps remain open until their complete named native and acceptance checks are observed.

## Ownership

- ansible/roles/hysteria/defaults/main.yml
- ansible/roles/hysteria/tasks/enable.yml
- ansible/roles/hysteria/templates/config.yaml.j2
- ansible/roles/hysteria/templates/hysteria-server.service.j2
- ansible/roles/hysteria/CLAUDE.md
- secrets/schema.json
- secrets/prod.secrets.example.yaml
- scripts/validate-secrets.py
- scripts/bootstrap-secrets.sh
- scripts/emit-singbox.sh
- scripts/emit-bundle.sh
- scripts/liveness_profiles.py
- scripts/check-singbox-client-compatibility.py
- scripts/check-liveness-profile-compatibility.py
- contract/ripdpi-bundle.schema.json
- ansible/playbooks/smoke-test.yml
- tests/unit/test_bundle_schema.py
- tests/unit/test_emit_singbox_roundtrip.py
- docs/CLIENT-NOTES.md
- docs/RIPDPI-BUNDLE.md
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [x] ANS-1791618091815754 Confirm exact ECH capability and implement the coordinated typed server recipient contract #feature @item:ANS-1791618083683925
- [x] ANS-1791618093172970 Deliver private authority generation secure emission and actual supported recipient integration #feature @item:ANS-1791618083683925
- [x] ANS-1791618094259404 Implement complete activation rotation and compensating failure behavior #feature @item:ANS-1791618083683925
- ANS-1791618095149688 DROPPED: Prove negotiated ECH authenticated delivery and negative cases then complete eligible source and staging gates #feature @item:ANS-1791618083683925

## Verification

- `mise exec -- python3 -m pytest -q tests/unit/test_bundle_schema.py tests/unit/test_emit_singbox_roundtrip.py tests/unit/test_hysteria_runtime_release.py`
- `make test-native-runtime`
- `make snapshot-check`
- `build-gate -- make check`
- `Existing when the qualified peer checkout is available: make task-federation PEER_ROOT=<RIPDPI-checkout>`
- `NEW make test-hysteria-ech-runtime; implementation must add exact supported recipient parser negotiated ECH traffic trust failures rotation and private-authority compensation to the native lane`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Native `make test-native-runtime` and the dependency-provided native acceptance targets run only on the explicitly isolated Linux root/systemd/TUN host. macOS or missing privileges are prerequisite failures, never silent skips or mocked substitutes.

Source preparation is authorized in a dedicated worktree. Promotion and acceptance still follow the canonical dependency graph; source changes alone do not check an execution step.
