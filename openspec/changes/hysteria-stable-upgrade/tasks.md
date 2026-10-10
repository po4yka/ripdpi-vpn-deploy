# SCR-1791618064422507: Upgrade Hysteria with validated congestion and UDP resource profiles

## Objective

Upgrade Hysteria with validated congestion and UDP resource profiles. All execution checkboxes remain open; this is planning, not implementation or deployment approval.

## Ownership

- secrets/prod.secrets.example.yaml
- secrets/schema.json
- scripts/validate-secrets.py
- scripts/bootstrap-secrets.sh
- scripts/ci-bootstrap-secrets.sh
- ansible/roles/hysteria/defaults/main.yml
- ansible/roles/hysteria/templates/config.yaml.j2
- ansible/roles/hysteria/tasks/enable.yml
- ansible/roles/hysteria/CLAUDE.md
- ansible/roles/baseline/defaults/main.yml
- ansible/roles/baseline/templates/sysctl-vpn.conf.j2
- ansible/roles/baseline/CLAUDE.md
- scripts/emit-singbox.sh
- scripts/emit-bundle.sh
- scripts/liveness_profiles.py
- scripts/check-singbox-client-compatibility.py
- tests/unit/test_hysteria_runtime_release.py
- tests/unit/test_runtime_audit_regressions.py
- docs/CLIENT-NOTES.md
- docs/TESTING.md
- .github/workflows/reproducible-build.yml
- Primary integration owns all shared schema, profile, Makefile, CI/snapshot and portfolio edits; explicitly assign disjoint paths before future parallel implementation.
- Preserve unrelated work, existing review records and private operator files. Use a dedicated implementation worktree only after authorization.
- This planning session has one serialized repository writer; delegated plan drafts do not alter runtime source.

## Execution

- [ ] SCR-1791618069580618 Refresh exact stable release and client inputs and update all pinned consumers coherently #feature @item:SCR-1791618064422507
- [ ] SCR-1791618070531675 Implement bounded congestion and baseline UDP resource profiles with exact native validation #feature @item:SCR-1791618064422507
- [ ] SCR-1791618071381219 Deliver measured authenticated traffic warm adoption and compensating rollback coverage #feature @item:SCR-1791618064422507
- [ ] SCR-1791618072302643 Complete reviewed source gates and define separately authorized 48-hour staging promotion evidence #feature @item:SCR-1791618064422507

## Verification

- `mise exec -- python3 -m pytest -q tests/unit/test_hysteria_runtime_release.py tests/unit/test_runtime_audit_regressions.py tests/unit/test_emit_singbox_roundtrip.py`
- `make snapshot-check`
- `make test-native-runtime`
- `build-gate -- make check`
- `NEW make test-hysteria-resource-profiles; implementation must add exact runtime parser tuning measurement warm-upgrade and compensating rollback cases to the native lane`

Requirement-to-step mapping and unfulfilled evidence categories live in verification.md. No fixture, refusal-only result or skipped selected case satisfies positive capability. Future external acceptance requires current authorization and exact scope; no existing cancelled task is revived.

Native `make test-native-runtime` and the dependency-provided native acceptance targets run only on the explicitly isolated Linux root/systemd/TUN host. macOS or missing privileges are prerequisite failures, never silent skips or mocked substitutes.

Implementation starts only after the canonical portfolio prerequisites are satisfied and separately authorized. Planning alone neither starts work nor checks an execution step.
