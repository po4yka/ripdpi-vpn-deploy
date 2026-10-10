## Context

Shared runtime-release verifies owned bytes and compensates its link publication, but returns committed before Xray or Hysteria2 configuration and service readiness are accepted. A later parser, asset, certificate, bind or startup failure leaves the active links selecting a rejected runtime. Existing nginx and geodata publication improvements do not establish a complete transport runtime transaction.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: commit transport runtimes only after complete configuration and readiness acceptance with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- Reuse shared runtime locking, root-owned staging, digest receipts, immutable release identities and no-follow publication; do not create a second deployment controller.
- The transport acceptance commit follows complete native validation and observed protocol readiness; link equality and is-active alone are not sufficient.
- Keep the previous distinct accepted generation across unchanged retries, including binary, assets, config, TLS and relevant enabled/active unit state.
- Candidate validation must name staged binary and asset paths rather than implicitly validating through already-published public links.
- Persistent recovery records containing private authority remain root-only and bounded; diagnostics publish categorical state and nonsecret identities only.
- Unknown or foreign recovery authority refuses without deletion. An unconfirmed restoration remains an incomplete transaction and cannot be reported as accepted.
- First-install failure leaves no enabled unaccepted transport; ordinary upgrades restore prior positive forwarding.

## Contracts and ownership

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
- Dependencies: None; may be implemented independently after baseline confirmation.. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- A full transaction crosses runtime-release and consumer role boundaries; recovery ordering and handler queues must be designed together.
- Service activation and compensation can interrupt sessions; bounded interruption must be explicit and measured.
- Power loss may interrupt several filesystem and process changes; a durable journal and deterministic retry are required rather than claiming multi-file atomicity.
- Recovering private config and TLS must not overwrite a foreign inode or discard independent operator work.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

Planning only, with future implementation approval required. Preserve existing runtime receipts and distinct archive/source identities, and define any receipt format change without compatibility shims. Existing accepted service state must be captured through trusted bounded inspection before transition; unknown legacy authority cannot silently become accepted. Integrated nginx/geodata transactions and review evidence stay intact. Upgrade and PQE evaluation depend on this capability, but neither upgrades nor PQE activation belong to this repair. Live adoption requires an exact authorized target, reviewed candidate and authenticated rollback proof.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-RTA-CANDIDATE`: Extend runtime-release consumer tests and NEW transport acceptance native fixtures; inject asset failure and semantic parser rejection after successful binary staging.
- `REQ-PROTO-RTA-ADOPTION`: NEW exact native service fixtures covering wrong TLS, occupied socket, startup error and active-but-broken protocol readiness.
- `REQ-PROTO-RTA-RECOVERY`: NEW kill-point tests plus existing runtime-release compensation coverage; assert complete bytes, inode ownership, unit state, protocol result and A-to-B-to-B previous identity.
- `REQ-PROTO-RTA-AUTHORITY`: Extend real local Ansible check-mode tests and NEW symlink/hardlink/foreign journal/privacy failure regressions.

## Validation commands

- `mise exec -- python3 -m pytest tests/unit/test_runtime_release_contract.py tests/unit/test_runtime_release_consumers.py tests/unit/test_hysteria_runtime_release.py tests/unit/test_xray_xhttp_only.py`
- `make snapshot-check`
- `build-gate -- make check`
- `NEW make test-transport-runtime-acceptance — Exercise exact owned native upgrade and rollback acceptance plus process-death recovery without real inventory.`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

## Supported native candidate validation

Xray candidate validation uses its supported native test command against the staged config and staged asset directory. Hysteria has no validation-only server flag: validate actual staged runtime and TLS by bounded server startup plus authenticated readiness in an invocation-owned isolated Linux namespace, using the intended sandbox and listener contract. YAML shape validation remains supplemental. Any uncertain cleanup or leaked process/socket refuses live activation and retains owned recovery evidence; never invent a check flag or bind candidate validation onto a real production listener.

## Canonical dependencies

- No new implementation prerequisite.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
