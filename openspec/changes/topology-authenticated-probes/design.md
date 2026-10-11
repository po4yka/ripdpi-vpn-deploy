## Context

Ordinary verification and watchdog still assume one legacy AWG interface, and Hysteria smoke omits enabled obfuscation and bypasses TLS verification. Effective cohorts and XHTTP backend ownership also need one consistent health model. Existing source fixes and synthetic service checks do not by themselves prove authenticated transport delivery or correct outage attribution.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: deliver topology-aware authenticated transport health and secure smoke probes with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- Use effective topology rather than secret intent or a fixed base port. The canonical binding resolver owns AWG selection; the already integrated REALITY probe manifest remains authoritative.
- XHTTP frontend and backend health are separate observations joined into one P1 result; a healthy nginx listener cannot mask a failed Xray backend and a shared backend must not cause unrelated frontend restarts.
- Hysteria smoke uses its own configured hostname before documented fallback, validates the certificate and mirrors Salamander. No insecure option is introduced as a test workaround.
- Keep invocation-owned client units, vacant local ports, bounded deadlines and cleanup uncertainty semantics. A foreign listener cannot satisfy a probe.
- Positive authenticated traffic and negative credential/trust cases are mandatory. Local controls diagnose failures but never substitute for a client data-plane result.
- Do not revive the cancelled external acceptance epic or retired observability topology. Add runtime tests to this runnable verification capability; live watches or remote probes need separately authorized scope.
- Current AWG runtime notifications, retirement and Hysteria redirect source fixes remain credited to their existing tasks. Named warm-adoption and hopped-traffic tests supplement them without altering historical verification records.

## Contracts and ownership

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
- Dependencies: awg-binding, awg-forwarding, xhttp-contract, schema. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- A topology resolver error can trigger unnecessary service restarts or mask a secondary instance outage.
- Probe credentials and target metadata can leak through subprocess arguments or results unless private boundaries remain explicit.
- Authenticated probes add traffic and operational load; frequency, deadlines and bounded concurrency must be explicit and configurable without unbounded loops.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

After implementation approval, replace single-target health assumptions across every ordinary verification and watchdog caller, preserving existing budgets and ownership files. Redistribute no credentials automatically. Roll out probe behavior only through separately authorized scope, record exact source and target identities, and keep prior authoritative restart state recoverable.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-PROBE-TOPOLOGY`: Executable manifest/verify/watchdog regression matrix for cohort-only, custom single-interface and multiple-instance layouts, plus XHTTP backend-only outage and shared-owner cases.
- `REQ-PROTO-PROBE-AUTH`: Exact Hysteria and supported client runtime tests with real certificates and obfuscation on/off; exact AWG and Xray authenticated positive and credential-negative cases.
- `REQ-PROTO-PROBE-OWNERSHIP`: Preserve smoke cleanup and watchdog notification/state suites; add actual stalled-client and exact recovery-target cases with verbose synthetic-secret leak assertions.
- `REQ-PROTO-PROBE-EVIDENCE`: Add exact binary Linux systemd/TUN/QUIC cases to the native lane; retain existing controller notification and retirement tests as distinct proof. Schema-test redacted evidence and stale-health replacement.

## Validation commands

- `mise exec -- python3 -m pytest -q tests/unit/test_watchdog_templates.py tests/unit/test_watchdog_protocol_probe.py tests/unit/test_smoke_test_cleanup.py tests/unit/test_runtime_audit_regressions.py`
- `make test-native-runtime`
- `make snapshot-check`
- `build-gate -- make check`
- `NEW make test-topology-authenticated-probes; implementation must add exact-client topology outage secure smoke warm-adoption and hopping cases to the native lane`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

Native `make test-native-runtime` and the dependency-provided native acceptance targets run only on the explicitly isolated Linux root/systemd/TUN host. macOS or missing privileges are prerequisite failures, never silent skips or mocked substitutes.

## Canonical dependencies

- `SCR-1791618039091425` — `awg-device-binding`.
- `ANS-1791618048083304` — `awg-forwarding-dualstack`.
- `XRY-1791617955392712` — `xhttp-endpoint-contract`.
- `SCT-1791617687019287` — `transport-input-semantics`.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
