## Context

The server exposes an optional alternate direct XHTTP frontend, but the recipient emitter advertises only the primary. XHTTP mode and advanced connection behavior are largely upstream defaults rather than a tested shared contract. The existing architecture can deliver explicit alternate selection and bounded performance profiles cheaply after endpoint correctness, isolation and safe runtime adoption are established.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. Implementation is authorized with local-only acceptance (2026-10-16).

## Goals / Non-Goals

- Goal: deliver selectable alternate xhttp endpoints and measured typed tuning with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: provider mutation, external staging, staging soak, physical or external clients, production deployment, actual credentials or unrelated cleanup.

## Decisions

- Alternate delivery is direct HTTPS and opt-in; its endpoint uses its configured hostname and port, not an assumed copy of the primary identity.
- Every emitted alternate is supported by its selected format and has a real server listener. Official sing-box remains free of unsupported XHTTP. RIPDPI carries auto/stream-up only. The native Xray format binds one loopback SOCKS listener per endpoint; all routing rules select one exact endpoint, with an unmatched blackhole default.
- Native Xray v26.3.27 admits auto, packet-up and stream-up. The optional bounded-pool profile requires stream-up and integer max_connections (1–4). It fixes request/age/session retirement to zero (unlimited reuse) so discarded HTTP pools cannot accumulate live sockets; native XMUX maps these controls directly. No extra JSON, unknown field, unsupported engine/version, unsafe retirement bound or ignored recipient tuning is accepted. Server XMUX is not emitted: these are connection-pool controls of the native outbound; server mode remains shared.
- Keep existing defaults. Qualify the optional profile through actual pinned native Xray processes in an owned disconnected local Linux lab: primary/alternate authenticated transfers, TLS and credential refusals, primary outage, idle recovery, reconnect, constrained transfer, process RSS and connection observations, and restored baseline. No external client acceptance or staging soak is required.
- Record active endpoint and failure class in redacted liveness evidence; do not automatically churn uTLS fingerprints or interrupt unrelated established sessions.
- P0 controls are a separate measured contract, not incidental additions to XHTTP tuning. Preserve classical REALITY shape, stable production release policy and the PQE HOLD guard.
- Unknown client support, prerelease-only controls or incomplete rollback keep the option unavailable for production. A future version upgrade is a separately reviewed coordinated server/client change.

## Contracts and ownership

- scripts/emit-singbox.sh
- scripts/liveness_profiles.py
- scripts/check-singbox-client-compatibility.py
- secrets/schema.json
- scripts/validate-secrets.py
- ansible/roles/xray/templates/config.json.j2
- ansible/roles/xray/defaults/main.yml
- ansible/roles/xray/CLAUDE.md
- ansible/roles/nginx-xhttp/tasks/enable.yml
- ansible/roles/nginx-xhttp/templates/site.conf.j2
- ansible/roles/nginx-xhttp/CLAUDE.md
- docs/CLIENT-NOTES.md
- docs/XRAY-RELEASE-LINE.md
- docs/PQ-REALITY-ADOPTION.md
- tests/unit/test_liveness_profiles.py
- tests/unit/test_relay_fallback.py
- tests/unit/test_secrets_schema.py
- NEW: tests/unit/test_xhttp_alternate_profiles.py
- NEW: tests/integration/xhttp_delivery_matrix/
- NEW: docs/XHTTP-DELIVERY-PROFILES.md
- Dependencies: xhttp-contract, runtime-transaction, boundary, integration. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation uses an authorized dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- The RIPDPI recipient engine and upstream Xray can differ in mode and advanced field support; exact compatibility must precede exposing a control.
- Aggressive reuse concurrency request limits or mode choices can increase idle failures memory usage connection counts or latency on constrained paths.
- Automatic fallback can obscure a broken primary; evidence must report actual selected endpoint and separate degraded delivery from fully healthy service.
- Publishing a second hostname can require private TLS/DNS prerequisites; planning and source tests do not authorize issuance or provider changes.
- PQE eligibility and new P0 controls are not inferred from XHTTP success, browser key shares or release notes alone.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

The user authorized local-only implementation and native Xray recipient format on
2026-10-16. No provider, inventory, secret decryption, external staging soak or
physical/external client run is part of acceptance. The independent four-protocol
acceptance task remains related roadmap work; this change owns its complete local
XHTTP matrix, rather than waiting for unrelated baseline transports.

The verification schema retains its existing categories: `staging` records only
the disconnected local Linux runtime staging harness; `client` records only the
pinned native fixture process. Neither category establishes external acceptance.
These categories are fulfilled through real local execution, not marked passed
by reclassifying a parser or mock as traffic evidence. Local and exact-source CI
checks remain required. The production pins, classical P0 and PQE HOLD remain.
Native Xray recipient JSON is a new explicit P1-only format; existing bundle and
subscription formats do not silently acquire XMUX settings. Distribute native
JSON only to the qualified engine. Unsupported RIPDPI tuning refuses publication.

## Acceptance tests

- `REQ-PROTO-XAT-ALTERNATE`: NEW test_xhttp_alternate_profiles.py plus exact client delivery matrix with distinct host/port, certificate mismatch, disabled listener and official unsupported-client cases.
- `REQ-PROTO-XAT-TYPED`: NEW schema and exact native profile matrix tests for each approved mode and bound, including explicit unsupported field/version rejection.
- `REQ-PROTO-XAT-MEASURED`: NEW credential-free xhttp_delivery_matrix using exact clients and deterministic controlled faults; preserve raw technical measurements and declared acceptance thresholds.
- `REQ-PROTO-XAT-ROLLBACK`: Reuse destination boundary and runtime acceptance native suites; add private artifact, bearer-log and unchanged PQE HOLD/classical-P0 guard regressions to the feature matrix.

## Validation commands

- `mise exec -- python3 -m pytest tests/unit/test_liveness_profiles.py tests/unit/test_relay_fallback.py tests/unit/test_secrets_schema.py`
- `make liveness-profile-check`
- `make snapshot-check`
- `build-gate -- make check`
- `make test-xhttp-delivery-matrix — Prove selectable alternate, exact typed modes, comparative measurements and rollback with owned client/server fixtures.`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

## Canonical dependencies

- `XRY-1791617955392712` — `xhttp-endpoint-contract`.
- `ANS-1791617913525586` — `runtime-acceptance-transaction`.
- `SEC-1791617841911853` — `resolved-destination-boundary`.
- Related, not a local XHTTP implementation blocker: `TST-1791618356595983` — `native-four-protocol-acceptance`.

The first three are accepted source prerequisites. The independent four-protocol task is a related roadmap item under the authorized local-only scope. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
