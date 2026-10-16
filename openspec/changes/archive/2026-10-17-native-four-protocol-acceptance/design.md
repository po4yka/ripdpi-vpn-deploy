## Context

Existing synthetic role fixtures and external sentinel capabilities cover different boundaries. Six original findings now have integrated source fixes, but warm daemon adoption, real hopping, default XHTTP completion and exact source regression still need a runnable isolated native acceptance contract.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: deliver isolated native acceptance for every baseline transport with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- Use disposable root/systemd/network namespaces or VMs, exact verified artifacts and real TUN/sockets; a shell stub cannot satisfy a native result.
- Reuse protocol-liveness emitters, binding and cleanup adapters; do not create another source of configuration truth or another provider deploy pipeline.
- Source-fixed A03/A07/A08/A09/A12/A14 remain mapped to their existing review tasks; this capability adds named missing proof and never overwrites their prior receipts.
- Pair positive authenticated HTTPS with meaningful TCP/UDP upload/download and DNS; wrong credentials and TLS names must refuse; shutdown must remove owned resources and preserve foreign ones.
- Native runner requires explicit supported Linux host prerequisites; unsupported local platform fails categorically. No skip or mock fallback counts as a positive capability.
- Baseline alternate-server acceptance uses a real client configuration derived from the canonical endpoint contract for the already-supported server listener. It does not advertise or certify delivered alternate-recipient selection, which is owned by the later xhttp-features change and must rerun full emitted-artifact/client acceptance. No dependency cycle or fixture-as-live claim is introduced.

## Contracts and ownership

- tests/unit/test_protocol_liveness.py
- tests/unit/test_liveness_profiles.py
- tests/unit/test_amneziawg_native_lifecycle.py
- tests/unit/test_nginx_transaction_native.py
- tests/unit/test_monitoring_logrotate.py
- ansible/molecule/full-stack/
- docs/TESTING.md
- Makefile
- NEW tests/native/transport_acceptance/ runner and fixtures
- NEW selected isolated Linux CI workflow integrated with the existing selector
- Dependencies: boundary, runtime-transaction, awg-binding, awg-forwarding, xhttp-contract, topology-probes, schema, targets. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- A published contract change may reject previously accepted inputs; update all consumers atomically and test unchanged supported inputs.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

This task implements a real isolated source acceptance capability. No provider or production resources are allocated. The cancelled external epic stays dropped; any future external run needs new exact scope and authorization.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-NATIVE-COMPLETION`: NEW native runner cases plus complete existing liveness and emitter suites; packet completion is required rather than socket/activity alone.
- `REQ-PROTO-NATIVE-LIFECYCLE`: Real upstream AWG on Linux TUN, recorded process identity and before/after traffic; inherited ownership fixtures remain supplemental.
- `REQ-PROTO-NATIVE-COMPENSATION`: Exact binaries, activation interruption cases, native logrotate execution and real served request log checks.
- `REQ-PROTO-NATIVE-HOPPING`: Actual nftables namespace rules, rendered systemd restrictions and native Hysteria clients; require controlled traffic witnesses.
- `REQ-PROTO-NATIVE-HONESTY`: NEW runner self-tests for failure paths and complete native CI run; no fake executable can fulfill this requirement.

## Validation commands

- `mise exec -- python3 -m pytest -q tests/unit/test_protocol_liveness.py tests/unit/test_liveness_profiles.py tests/unit/test_amneziawg_native_lifecycle.py tests/unit/test_nginx_transaction_native.py tests/unit/test_monitoring_logrotate.py`
- `NEW make transport-native-acceptance on the explicitly isolated Linux runner; all cases complete with zero skips and authenticated evidence`
- `build-gate -- make check`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

## Canonical dependencies

- `SEC-1791617841911853` — `resolved-destination-boundary`.
- `ANS-1791617913525586` — `runtime-acceptance-transaction`.
- `SCR-1791618039091425` — `awg-device-binding`.
- `ANS-1791618048083304` — `awg-forwarding-dualstack`.
- `XRY-1791617955392712` — `xhttp-endpoint-contract`.
- `MON-1791618056169855` — `topology-authenticated-probes`.
- `SCT-1791617687019287` — `transport-input-semantics`.
- `SCR-1791617975137354` — `reality-target-validation`.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
