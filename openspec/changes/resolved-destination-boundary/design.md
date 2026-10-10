## Context

Xray still routes domain destinations through its unconditional direct rule before IPIfNonMatch resolution, allowing Freedom to resolve and dial private addresses afterward. Hysteria2 lacks an equivalent complete recipient destination boundary. These failures violate local management and private network isolation even though public forwarding is intended. Previously integrated role, firewall and lifecycle fixes do not implement this resolved-address policy.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: enforce resolved destination isolation for p0 p1 and hysteria2 with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- Recipients may access public destinations. Deny IPv4 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16, 224.0.0.0/4 and 240.0.0.0/4, and IPv6 ::/128, ::1/128, fc00::/7, fe80::/10 and ff00::/8. Normalize IPv4-mapped IPv6 before policy evaluation. Trusted plumbing exceptions are never recipient-selected bypasses.
- Evaluate the final dial address with a consistent resolution contract. A mixed public/private answer may select only admissible addresses; every retried or newly resolved address must be checked again.
- Do not claim DNS rebinding protection from IPOnDemand alone, and do not add a hostname deny list as the substitute for address enforcement.
- Keep resolver and trusted cascade adapter internals distinct from recipient-selected destinations; any necessary exception must be narrow and tested.
- Prefer supported exact-runtime policy interfaces. If the pinned runtime cannot enforce the contract, resolve that capability gap explicitly rather than weakening the requirement or adding an unauthorized dependency.
- Security regression fixtures use owned local authorities and synthetic client material; transcripts never contain server keys, UUIDs, passwords or private endpoint inventories.

## Contracts and ownership

- ansible/roles/xray/templates/config.json.j2
- ansible/roles/xray/tasks/enable.yml
- ansible/roles/xray/CLAUDE.md
- ansible/roles/hysteria/templates/config.yaml.j2
- ansible/roles/hysteria/tasks/enable.yml
- ansible/roles/hysteria/CLAUDE.md
- scripts/validate-secrets.py
- tests/unit/test_secrets_schema.py
- NEW: tests/unit/test_transport_destination_boundary.py
- NEW: tests/integration/transport_destination_boundary/
- NEW: docs/TRANSPORT-DESTINATION-POLICY.md
- Dependencies: schema. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- Earlier name resolution can change DNS latency, resolver use, IPv4/IPv6 preference and public destination selection.
- A policy checked independently of outbound dialing can retain a rebinding race; exact-address binding is a required completion boundary.
- Overbroad private-address denial can break intended loopback classifier adapters or DNS internals if recipient traffic and trusted transport plumbing are not separated.
- Changing the destination contract intentionally removes access to private destinations; no compatibility bypass is retained.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

Planning only. Future implementation requires separate authorization and a dedicated worktree. Review the destination policy and exact runtime capability before editing code. Preserve the integrated source remediation and all review-task receipts. A later authorized rollout must regenerate and validate effective configuration, prove public forwarding and private isolation on staging, and retain an authenticated rollback to the previous complete runtime/configuration. No production destination exception or credential operation is authorized by this plan.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-RDB-POLICY`: NEW exact pinned-runtime test_transport_destination_boundary.py and integration fixtures; assert actual accepted traffic and absence of forbidden receiver traffic, not only rendered rule strings.
- `REQ-PROTO-RDB-DIAL`: NEW controlled resolver/dial sequencing regressions with multiple A and AAAA answers, retries, TTL changes and UDP destination variation.
- `REQ-PROTO-RDB-PLUMBING`: Extend Xray profile rendering and native controlled adapter tests with public completion and direct internal-destination refusal.
- `REQ-PROTO-RDB-FAILURE`: NEW parser/failure/no-secrets regressions plus integration restoration of accepted public forwarding.

## Validation commands

- `mise exec -- python3 -m pytest tests/unit/test_secrets_schema.py tests/unit/test_xray_xhttp_only.py`
- `make snapshot-check`
- `build-gate -- make check`
- `NEW make test-transport-destination-boundary — Run credential-free exact pinned-runtime isolation and positive public forwarding tests in owned namespaces.`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

## Canonical dependencies

- `SCT-1791617687019287` — `transport-input-semantics`.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
