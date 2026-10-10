## Context

Current JSON Schema and semantic checks accept a REALITY cohort without clients, invalid AWG parameter relationships, and Hysteria masquerade types the deployed validator refuses. This plan tightens the accepted contract instead of introducing unsupported modes.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: reject incoherent transport inputs before runtime mutation with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- Require clients in every explicit REALITY cohort; reject missing/unknown/duplicate references and define empty lists as invalid for an enabled listener.
- Normalize AWG instance names to the existing 1-15-character runtime grammar; reject Jmin greater than Jmax, colliding H1-H4 and duplicate or conflicting peer host identities. Legal routed prefixes require an explicit routed-peer contract and may not be mistaken for issued host addresses.
- Retain S3=S4=0 and the verified-floor guard; no version bump, I-field rollout or arbitrary JSON escape hatch.
- Keep masquerade_type proxy-only and validate an owned HTTPS origin consistently with the endpoint contract. Parent owns shared schema edits; all other changes request this lane.

## Contracts and ownership

- secrets/schema.json
- secrets/prod.secrets.example.yaml
- scripts/validate-secrets.py
- scripts/spot-check-secrets.py
- scripts/check-secrets-coverage.py
- ansible/roles/runtime-release/files/validate_yaml_mapping.py
- tests/unit/test_secrets_schema.py
- tests/unit/test_spot_check_secrets.py
- tests/unit/test_transport_config_lifecycle.py
- Dependencies: None; may be implemented independently after baseline confirmation.. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- A published contract change may reject previously accepted inputs; update all consumers atomically and test unchanged supported inputs.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

BREAKING: invalid cohort, AWG and masquerade inputs stop being accepted. Update all checked-in examples, emitters and consumer tests together; do not preserve a permissive legacy path. No private inputs are migrated by this planning request.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-INPUT-COHORT`: Extend test_secrets_schema.py with missing, empty, unknown and duplicate cohort cases and render every accepted document.
- `REQ-PROTO-INPUT-AWG`: Add top-level/instances boundary tests and native upstream parser acceptance; routed-subnet cases remain explicitly distinguished.
- `REQ-PROTO-INPUT-HYSTERIA`: Extend transport-config lifecycle and schema tests for accepted proxy and every unsupported mode.
- `REQ-PROTO-INPUT-PRIVACY`: Run complete secrets-schema, version-floor and coverage suites with marker redaction checks.

## Validation commands

- `mise exec -- python3 -m pytest -q tests/unit/test_secrets_schema.py tests/unit/test_spot_check_secrets.py tests/unit/test_transport_config_lifecycle.py tests/unit/test_amneziawg_version_floor.py`
- `mise exec -- python3 scripts/check-secrets-coverage.py`
- `build-gate -- make check`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

## Canonical dependencies

- No new implementation prerequisite.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
