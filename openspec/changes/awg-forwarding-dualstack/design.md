## Context

The single-instance firewall still forwards and masquerades only awg0 even when the supported role interface differs. Ordinary issued peers have one IPv4 identity while recipient configurations capture the IPv6 default route without provisioning or authorizing an IPv6 source. Independent fixed MTU values prevent an explicit constrained-path configuration.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: deliver interface-correct dual-stack amneziawg forwarding and configurable mtu with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- The canonical binding change owns identity resolution; this change extends that contract rather than adding a second resolver.
- Device address collections are typed by family and server AllowedIPs authorize both allocated host identities. Routed subnet peers remain explicitly distinct from device host addresses.
- Change the published single-CIDR contract and all consumers coherently. Require a qualified RIPDPI consumer task and federation validation before claiming cross-repository completion; no shim retains ambiguous old data.
- Support an explicit IPv4-only suppression profile where needed, but label it accurately; capture of ::/0 without successful IPv6 delivery never counts as dual-stack success.
- MTU is an explicit bounded configuration input, not automatic network diagnosis. Choose the supported bounds from exact runtime and client behavior; server and emitted client must agree.
- Keep one NAT counter comment per actual instance and preserve unrelated tables and default-drop forwarding. Do not grant broad forwarding or relax source authorization to make IPv6 pass.
- Planning-only approval is not implementation or infrastructure authorization. Physical client and staging tests must retain exact source and resource identity.

## Contracts and ownership

- ansible/roles/firewall/templates/nftables.conf.j2
- ansible/roles/firewall/CLAUDE.md
- ansible/roles/amneziawg/templates/awg0.conf.j2
- ansible/roles/amneziawg/defaults/main.yml
- ansible/roles/amneziawg/tasks/instances.yml
- ansible/roles/amneziawg/CLAUDE.md
- secrets/schema.json
- scripts/validate-secrets.py
- scripts/new-client.sh
- scripts/rotate-secrets.sh
- scripts/emit-awg.sh
- scripts/emit-bundle.sh
- scripts/liveness_profiles.py
- contract/ripdpi-bundle.schema.json
- docs/RIPDPI-BUNDLE.md
- docs/AWG-COHORTS.md
- tests/unit/test_firewall_egress_policy.py
- tests/unit/test_real_vps_awg_nat_lane.py
- tests/unit/test_bundle_schema.py
- Dependencies: awg-binding. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- Dual-stack address and bundle changes affect external consumers and need coordinated breaking migration.
- Removing IPv6 capture as a workaround would leak native IPv6 outside the tunnel; source and client failure tests must preserve lockdown.
- IPv6 routing, RA ownership, uplink availability and MTU differ between hosts; fail explicitly when prerequisites are absent rather than advertising unsupported delivery.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

After implementation approval and binding integration, migrate peer host identity into typed dual-family address collections, update every parser and regenerate profiles under separate credential authorization. Rollout first uses bounded staging with validated IPv6 uplink and recovery. Keep prior complete config usable for rollback and preserve unrelated instances. No live mutation occurs in planning.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-AWG-FORWARD`: Extend firewall render tests and add real nftables namespace enforcement with exact AWG clients, observing per-instance counters and return traffic.
- `REQ-PROTO-AWG-DUAL`: Exact server/client namespace tests plus qualified recipient parser round trips, separate IPv4 IPv6-only and DNS observations, and one-device revocation in each family.
- `REQ-PROTO-AWG-MTU`: Shared resolution boundary tests, exact client parser tests and controlled link-MTU namespace transfers; record throughput and loss instead of claiming an arbitrary preset optimal.
- `REQ-PROTO-AWG-NOLEAK`: Linux routing/nft packet capture plus supported physical recipient tests, failed activation compensation and prior-address/profile preservation assertions.

## Validation commands

- `mise exec -- python3 -m pytest -q tests/unit/test_firewall_egress_policy.py tests/unit/test_bundle_schema.py tests/unit/test_real_vps_awg_nat_lane.py`
- `make snapshot-check`
- `make test-native-runtime`
- `build-gate -- make check`
- `Existing when the qualified peer checkout is available: make task-federation PEER_ROOT=<RIPDPI-checkout>`
- `NEW make test-awg-dualstack-runtime; implementation must add authenticated dual-family TUN forwarding MTU and no-leak cases to the canonical native lane`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

## Physical baseline acceptance

Physical baseline acceptance uses the currently supported exact Android arm64 core with S3=S4=0; it does not depend on the later candidate upgrade. Record exact client/core/ABI/OS and interface MTU, perform three reconnect cycles, validate IPv4 and IPv6 DNS plus bidirectional TCP/UDP and IPv6-only targets, revoke the device and prove traffic stops, then disconnect and prove no traffic escapes the tunnel policy. A manually typed success record or fixture is not proof. This procedure and its bounded private evidence validator must be named in the operator acceptance surface; actual execution needs separate client/resource authorization.

`NEW make verify-awg-dualstack-client-evidence; validate invocation-bound evidence from the named physical baseline procedure, never manufacture a passing record`

Native `make test-native-runtime` and the dependency-provided native acceptance targets run only on the explicitly isolated Linux root/systemd/TUN host. macOS or missing privileges are prerequisite failures, never silent skips or mocked substitutes.

## Canonical dependencies

- `SCR-1791618039091425` — `awg-device-binding`.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
