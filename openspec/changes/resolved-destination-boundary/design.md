## Context

Xray still routes domain destinations through its unconditional direct rule before IPIfNonMatch resolution, allowing Freedom to resolve and dial private addresses afterward. Hysteria2 lacks an equivalent complete recipient destination boundary. These failures violate local management and private network isolation even though public forwarding is intended. Previously integrated role, firewall and lifecycle fixes do not implement this resolved-address policy.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. The current request authorizes source implementation after the transport-input commit, isolated tests, independent review, local commits and a PR. The user additionally selected a WARP UDP redesign; provider registration and deployment are not authorized.

## Goals / Non-Goals

- Goal: enforce resolved destination isolation for p0 p1 and hysteria2 with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: provider mutation, production deployment, actual credential operations, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- Recipients may access public destinations. Deny IPv4 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16, 224.0.0.0/4 and 240.0.0.0/4, and IPv6 ::/128, ::1/128, fc00::/7, fe80::/10 and ff00::/8. Normalize IPv4-mapped IPv6 before policy evaluation. Trusted plumbing exceptions are never recipient-selected bypasses.
- Evaluate the final dial address with a consistent resolution contract. A mixed public/private answer may select only admissible addresses; every retried or newly resolved address must be checked again.
- Remove the separate GeoIP private frontend rule: its extra asset ranges disagree with canonical literal/name admission under AsIs. Destination isolation remains enforced by the normalizer and final packet guard.
- Do not claim DNS rebinding protection from IPOnDemand alone, and do not add a hostname deny list as the substitute for address enforcement.
- Keep resolver and trusted cascade adapter internals distinct from recipient-selected destinations; any necessary exception must be narrow and tested.
- Prefer supported exact-runtime policy interfaces. If the pinned runtime cannot enforce the contract, resolve that capability gap explicitly rather than weakening the requirement or adding an unauthorized dependency.
- Security regression fixtures use owned local authorities and synthetic client material; transcripts never contain server keys, UUIDs, passwords or private endpoint inventories.
- Reuse the already pinned Xray runtime for dedicated private SOCKS TCP/UDP gateways. Main Xray and Hysteria frontends forward original recipient destinations to the guarded gateway; Hysteria-only profiles install the shared runtime without activating a REALITY frontend.
- The pinned Freedom UDP writer restricts fresh domain lookups to its IPv6-wildcard local socket family; an IPv4-only new domain in an existing association fails despite being public. A trusted standard-library metadata normalizer binds each association/name/port target to one admitted canonical literal before native gateway forwarding, preserving IPv4, IPv6 and mapped representations without an engine fork or new production dependency. Each packet rechecks the bound literal against policy; new targets, associations, reconnects and policy generations resolve again.
- The normalizer has a distinct unprivileged identity, typed per-frontend authentication/admission and bounded protocol/session/lookup resources. It performs no final recipient dial: its network authority is limited to fixed backend gateways, explicit numeric DNS plumbing and verified frontend replies. Direct and WARP paths remain distinct; the direct gateway gains no private outbound exception.
- The direct gateway has its own unprivileged UID, separate SOPS-owned internal authentication, explicit public numeric DNS servers with all forbidden answers filtered, and Freedom `ForceIP`. No system-DNS fallback, wildcard listener, configurable outbound source binding or trusted private outbound exception is permitted.
- Install early listener admission and an independent late final UID-deny OUTPUT hook after conntrack and all admitted destination rewrites. Earlier ACCEPT verdicts cannot bypass a later base-chain rejection. Reject unknown same/later OUTPUT mutation, incompatible POSTROUTING/route rewriting and unadmitted offload authority; a priority number alone is insufficient. Restrict gateway admission to managed frontend UIDs. Gateway UID exceptions allow only replies from the fixed listener port to the verified IPC tuple in conntrack reply direction; all other forbidden destinations are rejected.
- Validate the listener port against the effective ephemeral allocation range and existing reservations, and verify exclusive TCP/UDP ownership. Preserve unrelated reservations. This trusts the pinned gateway executable and root-owned fixed configuration; arbitrary code execution under its UID is outside this boundary.
- WARP UDP uses a second exact-Xray gateway inside an owned network namespace and the existing vendor service in `tunnel_only` mode. The vendor proxy's UDP ASSOCIATE support is unproven and is not a dependency. The main frontend routes WARP traffic directly to this namespace gateway, without giving the direct gateway a private WARP exception.
- Namespace gateway policy rejects forbidden IPv4/IPv6 destinations and permits public destination traffic only through the verified owned WARP TUN interface. Tunnel loss or reconnect cannot fall back to plaintext underlay routing. Root vendor tunnel transport is distinct from the unprivileged recipient gateway.
- Preserve the single owned vendor service and its registration state. A systemd network-namespace drop-in narrows the existing vendor authority; do not launch a second daemon against the same private state or add capabilities to either Xray gateway. Reject unrecorded service/namespace ownership.
- Selectively deny gateway access to effective SSH, recovery and control ports on owned host addresses, including public/floating endpoints. Preserve remote public SSH and owned public web forwarding. The WARP namespace imports the root-owned host-address set and checks it before admission.
- Resolve service identities before firewall rendering; install and verify policy before gateway/frontends start. Frontends bind their lifetime to the required gateways. Retire frontends and gateways before removing policy or namespaces. Fresh check-mode remains non-mutating and cannot invent UID, listener or tunnel readiness.
- Remove recipient port-53 `dns-out` interception: recipient DNS uses the guarded path to its requested public authority, including TCP/UDP and non-address records. Preserve engine/trusted DNS separately with explicit public numeric upstreams; the DNS-morph research scope is unchanged. This is an intentional published DNS behavior break.
- Apply the same normalized address policy to the trusted TCP classifier's actual literal connect boundary, retaining its public path without enabling a disabled or cancelled classifier rollout.


- Protected Xray frontend identity is fixed at xray:xray; alternative user/group overrides refuse before mutation rather than disagreeing with kernel UID admission. Frontend units and candidate validation select verified immutable executable paths. Bundled Xray assets use the immutable archive release directory. Installer CLI/current links do not select the accepted daemon after a rejected pin change; independent geodata publication retains its existing paired transaction.
- WARP vendor isolation requires the running systemd manager at version 257 or later for its private PID namespace. Refuse unsupported managers and in-place vendor-package upgrades while claimed registration exists; neither condition silently loosens the sandbox.
- The inert classifier uses a dedicated unprivileged UID and a final packet destination boundary after admitted rewrites, with only its exact local reply tuple excepted. The classifier authority is fixed at 127.0.0.1:10808. Reject alternate endpoints before publication. Reject purely numeric interface names because nftables interface-index serialization would be ambiguous after link removal.

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
- NEW: docs/TRANSPORT-EGRESS.md
- NEW: private transport-egress role, canonical destination policy, metadata normalizer and owned readiness/lifecycle helpers
- ansible/roles/firewall/, ansible/roles/warp-outbound/ and ansible/roles/xray-runtime/
- ansible/playbooks/site.yml and transport lifecycle/rotation surfaces
- secrets/schema.json and secrets/prod.secrets.example.yaml internal-authority contract
- scripts/cascade-classifier-proxy.py and shared literal-connect policy
- Shared template rendering/profile helpers, CI dependency selection, native prerequisites and snapshots
- Dependencies: schema. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Native adapter constraints

- Native SOCKS CONNECT success precedes final Freedom dialing. The normalizer selects one admitted canonical literal and never replays application bytes to another address. A reconnect evaluates resolution again; a published SOCKS reply is not final-dial evidence.
- Native UDP authorization and dispatcher mappings outlive the TCP control socket, and responses refresh inactivity. Retain both frontend and upstream UDP sockets after closure, drain and discard late packets, and require 240 seconds of continuous quiet before reusing either tuple. Any packet resets its quiet deadline. This source-derived margin requires the real stale-response test; busy tuples are never released to satisfy a hard age or resource ceiling.
- Store only the selected canonical literal in bounded per-association/name/port bindings, with no raw-answer or global DNS cache. Existing flows may retain a public literal after DNS changes; fresh bindings must reject newly private answers. Test repeated named UDP throughput without one NSS transaction per datagram.
- Preserve active TCP/UDP streams beyond five minutes. Use accepted-traffic idle timers aligned with the existing runtime contract; malformed or denied input does not refresh activity. An unconditional 300-second hard lifetime is excluded.
- Bound live and retired socket counts, target bindings, queued packets, resolver processes and drain work. Exhaustion refuses boundedly without reusing an unsafe tuple. Internal SOCKS tuple pairing protects retired relay boundaries; application UDP cryptographic identity and replay protection remain application responsibilities.
- Normalizer process loss invalidates its in-memory quarantine. Reset both paired gateways before admitting a fresh association generation. Test process death, definitive old-gateway teardown and autonomous recovery of enabled owned frontends; lifetime binding alone does not restart a stopped frontend.

## Risks / Trade-offs

- Earlier name resolution can change DNS latency, resolver use, IPv4/IPv6 preference and public destination selection.
- A policy checked independently of outbound dialing can retain a rebinding race; exact-address binding is a required completion boundary.
- Overbroad private-address denial can break intended loopback classifier adapters or DNS internals if recipient traffic and trusted transport plumbing are not separated.
- Changing the destination contract intentionally removes access to private destinations; no compatibility bypass is retained.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

BREAKING: authenticated proxy recipients lose private-address access; internal gateway authority becomes required for enabled proxy transports; recipient port-53 traffic retains its requested public DNS authority instead of being intercepted by native `dns-out`. The optional WARP path changes from vendor proxy mode to an isolated tunnel-only backend. Implement in the current dedicated worktree after the input-semantics commit. Review exact runtime and host ownership before activation. Preserve the integrated source remediation and all review-task receipts. A later authorized rollout must regenerate internal authority and effective configuration, prove public forwarding and private isolation on staging, and retain an authenticated rollback to the previous complete runtime/configuration and owned namespace state. No production destination exception or credential operation is authorized by this plan.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-RDB-POLICY`: NEW exact pinned-runtime test_transport_destination_boundary.py and integration fixtures; assert actual accepted traffic and absence of forbidden receiver traffic, not only rendered rule strings.
- `REQ-PROTO-RDB-DIAL`: NEW controlled resolver/dial sequencing regressions with multiple A and AAAA answers, retries, TTL changes and UDP destination variation.
- `REQ-PROTO-RDB-PLUMBING`: Extend Xray profile rendering and native controlled adapter tests with public completion and direct internal-destination refusal.
- `REQ-PROTO-RDB-FAILURE`: NEW parser/failure/no-secrets regressions plus integration restoration of accepted public forwarding.

## Validation commands

- `mise exec -- python3 -m pytest tests/unit/test_secrets_schema.py tests/unit/test_xray_xhttp_only.py`
- `make snapshot-check`
- `build-gate -- env CARGO_BUILD_JOBS=2 CMAKE_BUILD_PARALLEL_LEVEL=4 mise exec -- make check`
- `make test-transport-destination-boundary — Run credential-free exact pinned-runtime isolation and positive public forwarding tests in owned namespaces.`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

## Canonical dependencies

- `SCT-1791617687019287` — `transport-input-semantics`.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.

## WARP acceptance boundary

The exact example package exposes `tunnel_only` in an offline, network-disabled CLI probe. That supports the selected all-protocol transport interface but does not prove a registered vendor tunnel works. Native source acceptance must use real Xray clients, nftables, namespaces and tunnel-shaped packet paths, including disappearance/reconnect and no-underlay-leak cases. Such evidence must never be presented as real Cloudflare WARP acceptance.

Actual vendor TCP/UDP acceptance requires a separately authorized registered disposable environment. No registration, connection, production state access or provider action is included in this source request. Keep that evidence required and the WARP integration unclosed while it is absent; positive direct transport acceptance remains separately observable. Do not downgrade WARP UDP to direct or TCP-only as a substitute.
