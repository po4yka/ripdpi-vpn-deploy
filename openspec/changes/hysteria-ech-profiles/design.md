## Context

ECH is a grounded optional transport evolution, but the current server/client emission contract has no coordinated ECH authority, recipient capability check or real connection proof. A server-only option or unsupported-engine refusal would not deliver the feature and could break secure recipient connections.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: deliver coordinated hysteria ech server and recipient profiles with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- The parser-upgrade change owns stable sing-box 1.14.3 adoption and its release-age eligibility. This feature consumes its supported actual parser instead of independently upgrading or assuming the candidate works.
- Implementation begins with exact-version API and supported recipient capability confirmation, using execution-time refreshed official release and parser metadata. No guessed ECH field names or config encodings enter the contract.
- The feature is optional and bound to an explicit technical profile. Inner certificate identity, outer public identity, DNS discovery/public configuration distribution and owned masquerade semantics must be stated before implementation.
- Deliver at least one actual supported recipient parser and real ECH authenticated connection. Refusing unsupported engines is a required failure behavior but refusal-only output cannot complete the feature.
- Server private ECH keys remain encrypted and outside public bundles, process arguments, logs and callback output. Recipients receive only the public configuration needed by their supported engine.
- A qualified RIPDPI consumer task is mandatory if RIPDPI recipients are in the selected support set; federation and exact consumer parser/connection proof gate cross-repository completion.
- Certificate verification remains enabled. Silent fallback to plaintext ClientHello or insecure TLS is not permitted in an ECH-required profile; any intentionally permitted non-ECH profile is separately named and accurately observed.
- ECH changes affect packet identity and config lifecycle, not public admin exposure. Keep the unprivileged service and firewall-owned hopping; do not activate a traffic API or add unrelated transports.
- Current stable server/client eligibility and 48-hour staging requirements apply. Planning authorizes no key generation, issuance, physical installation, PR publication or deployment.

## Contracts and ownership

- ansible/roles/hysteria/defaults/main.yml
- ansible/roles/hysteria/tasks/enable.yml
- ansible/roles/hysteria/templates/config.yaml.j2
- ansible/roles/hysteria/templates/hysteria-server.service.j2
- ansible/roles/hysteria/CLAUDE.md
- secrets/schema.json
- secrets/prod.secrets.example.yaml
- scripts/validate-secrets.py
- scripts/bootstrap-secrets.sh
- scripts/emit-singbox.sh
- scripts/emit-bundle.sh
- scripts/liveness_profiles.py
- scripts/check-singbox-client-compatibility.py
- scripts/check-liveness-profile-compatibility.py
- contract/ripdpi-bundle.schema.json
- ansible/playbooks/smoke-test.yml
- tests/unit/test_bundle_schema.py
- tests/unit/test_emit_singbox_roundtrip.py
- docs/CLIENT-NOTES.md
- docs/RIPDPI-BUNDLE.md
- Dependencies: hysteria-upgrade, parser-upgrade, runtime-transaction. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- Client engines may support different ECH encodings or discovery paths; native parsing alone does not demonstrate negotiated encrypted ClientHello.
- ECH public configuration rotation can strand clients unless exact generation semantics, overlap policy and complete rollback are designed explicitly without a hidden compatibility shim.
- Inner/outer identity or DNS assumptions may weaken the owned masquerade profile or produce new classification signals; controlled packet observations and connection tests must establish actual behavior.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

After separate implementation approval, confirm the supported exact server and recipient API set, create encrypted ECH authority under explicit credential authorization, and update every selected parser/emitter together. Existing classical profiles remain a separately declared support choice rather than a hidden fallback inside ECH-required profiles. Validate complete candidate and rollback locally, then perform a separately authorized bounded 48-hour staging soak with real recipients before any production promotion.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-ECH-CONTRACT`: Exact native server and recipient parser/connection matrix, schema boundaries and qualified RIPDPI integration if included; placeholders and refusal-only tests are insufficient.
- `REQ-PROTO-ECH-PRIVATE`: Packet capture and exact client telemetry establish negotiated ECH; real wrong-SAN/untrusted certificate cases and verbose synthetic-key leak regressions enforce privacy.
- `REQ-PROTO-ECH-ACTIVATE`: Real private-file and systemd compensation/intent tests with exact Hysteria connections; wrong-key, unsafe-path and interrupted-publication cases preserve prior generation.
- `REQ-PROTO-ECH-ACCEPT`: NEW exact ECH native target plus separately authorized supported-recipient staging procedure, negotiated packet observations and guarded cleanup evidence.

## Validation commands

- `mise exec -- python3 -m pytest -q tests/unit/test_bundle_schema.py tests/unit/test_emit_singbox_roundtrip.py tests/unit/test_hysteria_runtime_release.py`
- `make test-native-runtime`
- `make snapshot-check`
- `build-gate -- make check`
- `Existing when the qualified peer checkout is available: make task-federation PEER_ROOT=<RIPDPI-checkout>`
- `NEW make test-hysteria-ech-runtime; implementation must add exact supported recipient parser negotiated ECH traffic trust failures rotation and private-authority compensation to the native lane`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

Native `make test-native-runtime` and the dependency-provided native acceptance targets run only on the explicitly isolated Linux root/systemd/TUN host. macOS or missing privileges are prerequisite failures, never silent skips or mocked substitutes.

## Canonical dependencies

- `SCR-1791618064422507` — `hysteria-stable-upgrade`.
- `TST-1791618376497512` — `stable-client-parser-upgrade`.
- `ANS-1791617913525586` — `runtime-acceptance-transaction`.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
