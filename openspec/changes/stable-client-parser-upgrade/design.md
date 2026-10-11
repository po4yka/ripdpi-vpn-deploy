## Context

The repository parser baseline is sing-box 1.13.16 while the fresh public release snapshot on 2026-10-10 identifies stable 1.14.3. Changing a parser pin must demonstrate exact consumer compatibility, not infer protocol support from a newer tag.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: upgrade verified recipient parsers to the current stable client line with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- Candidate stable sing-box1.14.3 is a planning snapshot only; recheck stable status, architecture hashes and migration notes at execution.
- Use official parser for its supported formats and exact Xray/RIPDPI engines for XHTTP/AWG-specific contracts. Do not falsely credit official sing-box with an unsupported transport.
- Change installer version and digests atomically, verify bytes before execution, and test tampered/truncated artifacts and unavailable architecture.
- Keep this source/toolchain migration independent of the pending vpnd rewrite; preserve Make as canonical surface.
- Refresh channel, publication time, immutable hashes and relevant advisories at execution. At least 48 hours of stable publication eligibility is required before production recipient redistribution or promotion; verified source/parser adoption may complete independently and authorizes no redistribution. Unknown or insufficient age is ineligible for promotion, not proof that parsing is unavailable.

## Contracts and ownership

- scripts/check-singbox-client-compatibility.py
- tests/unit/test_emit_singbox_roundtrip.py
- tests/unit/test_liveness_profiles.py
- docs/TESTING.md
- tools/tasking or unrelated vpnd migration are OUT OF SCOPE
- .github/workflows/ci.yml
- .github/actions/setup-disposable-ci/action.yml
- scripts/ci-real-deploy.py
- Makefile
- All exact-version expected-value tests discovered from the existing sing-box pin; runtime/source code unrelated to parser consumers is out of scope
- Dependencies: integration, schema, xhttp-contract, awg-binding. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- A published contract change may reject previously accepted inputs; update all consumers atomically and test unchanged supported inputs.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

Do not change runtime protocol defaults merely to satisfy a parser. Migrate actual removed contracts with every caller and explicitly record the break. No production/client redistribution is authorized by creating this plan.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-PARSER-INTEGRITY`: Installer transaction and checksum failure tests with verified real candidate version output.
- `REQ-PROTO-PARSER-PAYLOADS`: Complete emit_singbox_roundtrip and liveness suites plus native-four-protocol acceptance on old/candidate inputs.
- `REQ-PROTO-PARSER-ROLLBACK`: Actual installed-tool rollback and complete hosted parser/native jobs with exact-SHA evidence.
- `REQ-PROTO-PARSER-ELIGIBILITY`: Deterministic release-age boundaries, unknown metadata and advisory cases; actual candidate parser/native compatibility remains a separate mandatory gate.

## Validation commands

- `mise exec -- python3 -m pytest -q tests/unit/test_emit_singbox_roundtrip.py tests/unit/test_liveness_profiles.py`
- `Dependency-provided make transport-native-acceptance on isolated Linux with recorded candidate client identities`
- `build-gate -- make check`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

## Canonical dependencies

- `TST-1791618356595983` — `native-four-protocol-acceptance`.
- `SCT-1791617687019287` — `transport-input-semantics`.
- `XRY-1791617955392712` — `xhttp-endpoint-contract`.
- `SCR-1791618039091425` — `awg-device-binding`.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
