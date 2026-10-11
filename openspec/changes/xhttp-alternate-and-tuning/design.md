## Context

The server exposes an optional alternate direct XHTTP frontend, but the recipient emitter advertises only the primary. XHTTP mode and advanced connection behavior are largely upstream defaults rather than a tested shared contract. The existing architecture can deliver explicit alternate selection and bounded performance profiles cheaply after endpoint correctness, isolation and safe runtime adoption are established.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: deliver selectable alternate xhttp endpoints and measured typed tuning with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- Alternate delivery is direct HTTPS and opt-in; its endpoint uses its configured hostname and port, not an assumed copy of the primary identity.
- Every emitted alternate is supported by the selected exact client engine and has a real server listener. Standard official sing-box output remains free of unsupported XHTTP.
- Define named technical profiles from a small typed allowlist of mode and supported XMUX/request/connection limits after verifying exact engine capabilities. No arbitrary extra JSON or silently ignored fields are accepted.
- Keep existing defaults until comparative actual-client evidence supports a selected profile. A parser-only or refusal-only state does not deliver the feature.
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
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
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

Planning only. Future implementation requires separate approval. Land endpoint correctness, resolved isolation and complete runtime acceptance first. Determine exact server and supported recipient versions from primary release and parser evidence at implementation time; do not invent an upgrade pin now. Extend existing artifacts and consumers together without keeping duplicate contracts. Coordinate supported client redistribution before enabling a new mode/profile; ordinary defaults and the classical P0 path remain the accepted baseline until measured staging proof. PQE over REALITY stays HOLD and needs its own reviewed phase transition, client migration and authenticated rollback. Typed P0 controls may be evaluated later, but are outside this feature's runnable scope. No production promotion, DNS/TLS issuance or credential export is authorized.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

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
- `NEW make test-xhttp-delivery-matrix — Prove selectable alternate, exact typed modes, comparative measurements and rollback with owned client/server fixtures.`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

## Canonical dependencies

- `XRY-1791617955392712` — `xhttp-endpoint-contract`.
- `ANS-1791617913525586` — `runtime-acceptance-transaction`.
- `SEC-1791617841911853` — `resolved-destination-boundary`.
- `TST-1791618356595983` — `native-four-protocol-acceptance`.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
