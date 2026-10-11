## Context

The example still pins Hysteria v2.9.0 while the researched stable candidate is app/v2.13.0. Current bandwidth and QUIC windows are fixed and baseline lacks explicit UDP buffer controls. A pin-only edit would not prove real secure clients, hopping, resource limits, runtime adoption or rollback, nor establish whether supported congestion settings improve the selected technical path.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: upgrade hysteria with validated congestion and udp resource profiles with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- The boundary change owns private-destination isolation, runtime-transaction owns complete activation compensation, and baseline integration owns exact four-protocol proof. These dependencies must be satisfied before this candidate upgrade; no already integrated source task is used as a blocker.
- Candidate v2.13.0 is a proposed exact input, not automatic latest tracking. Refresh release API status, asset hashes, critical/high advisories and supported configuration signatures immediately before implementation and again before deployment.
- Production eligibility requires a non-prerelease candidate published for at least 48 hours and a separately authorized 48-hour bounded staging soak with no blocking regression or advisory. Unmet age or soak blocks promotion, not source research.
- Client parser/runtime compatibility must be tested against exact supported inputs. The newly researched sing-box 1.14.3 is a candidate requiring the same execution-time refresh and 48-hour eligibility, not implicit authorization to replace an existing pin.
- Do not guess congestion API names from older releases. Record the exact parser-supported settings and model required server/client interactions before rendering them.
- UDP kernel buffer controls belong to baseline. Mandatory hardening remains fatal, optional performance support may be classified only through its existing explicit exception boundary.
- Keep firewall-owned hopping and CAP_NET_BIND_SERVICE-only Hysteria. No NET_ADMIN, fake TCP mode, public traffic API or broad exposure is introduced by this upgrade.
- Leave existing private-destination isolation and masquerade safety requirements intact and block capability acceptance if supported client security is incomplete.
- Planning permits no implementation or deployment. A source-ready candidate, a measured native profile, staging eligibility and production rollout are separate states.

## Contracts and ownership

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
- Dependencies: boundary, runtime-transaction, topology-probes, integration. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- Congestion defaults or protocol behavior can change across the version gap and cause unfairness, high memory use or compatibility regressions.
- Larger UDP ceilings and receive windows may increase resource pressure; acceptance must include constrained memory and multiple clients, not only peak throughput.
- Candidate sing-box 1.14.3 may not meet the 48-hour publication requirement yet; verify real execution-time age rather than assuming readiness.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

Following implementation approval, refresh exact stable inputs, update all generators and fixtures coherently, and prove parser/client and rollback behavior. Default profiles retain reviewed resource bounds unless measurements justify a change. A separately authorized disposable staging run completes the 48-hour eligibility window and cleanup before any separately authorized production promotion. Keep prior pinned artifacts and complete configuration for compensating rollback.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-HY-VERSION`: Version-consumer consistency, digest rejection and exact native parser cases; recorded execution-time refresh and staging eligibility are separate from unit fixture assertions.
- `REQ-PROTO-HY-TUNING`: Schema boundary tests, exact binary startup under rendered sandbox, effective sysctl inspection and coordinated client configuration tests.
- `REQ-PROTO-HY-MEASURE`: NEW measured runtime target with controlled Linux network impairment and two real clients; do not silently skip required modes or substitute a fixture server.
- `REQ-PROTO-HY-UPGRADE`: Extend real runtime-release adoption/compensation cases with exact Hysteria sockets, secure trust, Salamander and multi-port traffic; capture process identity instead of invoking only the new installed command.

## Validation commands

- `mise exec -- python3 -m pytest -q tests/unit/test_hysteria_runtime_release.py tests/unit/test_runtime_audit_regressions.py tests/unit/test_emit_singbox_roundtrip.py`
- `make snapshot-check`
- `make test-native-runtime`
- `build-gate -- make check`
- `NEW make test-hysteria-resource-profiles; implementation must add exact runtime parser tuning measurement warm-upgrade and compensating rollback cases to the native lane`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

Native `make test-native-runtime` and the dependency-provided native acceptance targets run only on the explicitly isolated Linux root/systemd/TUN host. macOS or missing privileges are prerequisite failures, never silent skips or mocked substitutes.

## Canonical dependencies

- `SEC-1791617841911853` — `resolved-destination-boundary`.
- `ANS-1791617913525586` — `runtime-acceptance-transaction`.
- `MON-1791618056169855` — `topology-authenticated-probes`.
- `TST-1791618356595983` — `native-four-protocol-acceptance`.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
