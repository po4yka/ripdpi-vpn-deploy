## Context

Current examples pin Go v0.2.12 and tools v1.0.20241018, while researched candidate tags are v3.1.20260828 and v3.1.20260812. The source and client version gap requires semantic, toolchain and physical compatibility proof. Installed binary receipts and controller restart dispatch do not demonstrate warm running-process adoption or preserved real tunnel behavior.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: upgrade pinned amneziawg sources with unchanged reviewed wire settings with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- Baseline integration validates the existing exact wire/runtime versions before this new candidate pair. The runtime transaction change owns durable complete adoption and compensation; reuse it and do not create an upgrade-to-integration dependency cycle.
- Go v3.1.20260828 and tools v3.1.20260812 are candidate inputs, not proven compatible or stable merely because their tags exist. Refresh release/tag API status, resolved immutable commits, provenance, advisory status and toolchain requirements before source implementation and deployment.
- Production eligibility requires reviewed stable channel provenance, at least 48 hours since published candidate metadata and a separately authorized 48-hour staging soak. Unresolved release-channel or publication metadata prevents promotion.
- Keep current reviewed wire parameters. Do not enable RandomTrailers, DisableCookies, nonzero S3/S4 or new packet modes as part of this upgrade.
- S3/S4 candidate and verified safe floors remain unchanged. Physical acceptance of zero-S3/S4 candidates cannot be used to infer that nonzero transport junk is safe.
- Bind the exact client embedded core version, ABI and packet/header semantics to compatibility evidence. Update a qualified RIPDPI consumer task and federation checks if its source or published semantic contract must change.
- Preserve the existing ownership-aware instance retirement and source-build transaction. Add only necessary build/API changes and real adoption proof, not a duplicate lifecycle framework.
- Build toolchain versions and Go module inputs must be explicit and reviewed; do not rely on unrecorded automatic toolchain fetches to establish reproducibility.
- Every heavy local build uses the machine-wide build gate and existing job ceilings. Planning authorizes no builds, credentials, physical installation or live staging.

## Contracts and ownership

- secrets/prod.secrets.example.yaml
- scripts/bootstrap-secrets.sh
- scripts/ci-bootstrap-secrets.sh
- secrets/schema.json
- ansible/roles/amneziawg/tasks/enable.yml
- ansible/roles/amneziawg/templates/awg-quick@.service.j2
- ansible/roles/amneziawg/handlers/main.yml
- ansible/roles/amneziawg/CLAUDE.md
- ansible/roles/runtime-release/tasks/source-build.yml
- scripts/emit-sbom.py
- contract/cohort-fingerprint.golden.json
- contract/amneziawg-arm64-version-floor.json
- scripts/check-amneziawg-arm64-upstream.py
- tests/unit/test_amneziawg_source_pins.py
- tests/unit/test_amneziawg_native_lifecycle.py
- tests/unit/test_transport_p2_lifecycle.py
- tests/unit/test_amneziawg_version_floor.py
- docs/AWG-COHORTS.md
- docs/CLIENT-NOTES.md
- docs/TESTING.md
- Dependencies: awg-binding, runtime-transaction, integration. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- The v3-family source jump may change header and packet semantics even when configuration names appear identical.
- Old embedded client cores may not interoperate with selected candidate sources; successful server compilation is insufficient.
- Physical Android arm64 is mandatory for candidate acceptance; unavailable hardware or client artifact leaves promotion incomplete without fabricated proof.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

After implementation approval, refresh and select a compatible exact source pair and toolchain, update all pin consumers and exercise old reviewed wire settings with real clients. Preserve previous source receipts and complete config for rollback. Promotion waits for physical arm64 candidate proof and a separately authorized 48-hour staging soak. No private credential rotation or S3/S4 floor relaxation is implicit.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-AWG-VERSION`: Source-consumer consistency, real exact-source builds, immutable-ref rejection and receipt output checks; metadata and soak claims require separate observed evidence.
- `REQ-PROTO-AWG-WIRE`: Exact upstream parser and packet-capture interoperability matrix, fingerprint goldens and existing version-floor tests; compare actual bytes and offsets, not release-note assertions.
- `REQ-PROTO-AWG-ADOPT`: Extend native lifecycle to exact real AWG daemons and TUN traffic, inspect running executable identity and service restrictions, and inject candidate build/start/readiness failures.
- `REQ-PROTO-AWG-ARM64`: Named physical test procedure integrated with candidate evidence; no emulator, synthetic data or local server fixture substitutes for hardware proof.

## Validation commands

- `mise exec -- python3 -m pytest -q tests/unit/test_amneziawg_source_pins.py tests/unit/test_transport_p2_lifecycle.py tests/unit/test_amneziawg_version_floor.py`
- `make test-native-runtime`
- `make snapshot-check`
- `build-gate -- make check`
- `Existing when the qualified peer checkout is available: make task-federation PEER_ROOT=<RIPDPI-checkout>`
- `NEW build-gate -- make test-awg-source-candidate; implementation must add exact source-pair build interoperability and warm-adoption tests using existing job ceilings`
- `NEW make verify-awg-arm64-candidate; implementation must validate explicit physical candidate evidence without changing the S3/S4 safe floor`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

Native `make test-native-runtime` and the dependency-provided native acceptance targets run only on the explicitly isolated Linux root/systemd/TUN host. macOS or missing privileges are prerequisite failures, never silent skips or mocked substitutes.

## Canonical dependencies

- `SCR-1791618039091425` — `awg-device-binding`.
- `ANS-1791617913525586` — `runtime-acceptance-transaction`.
- `TST-1791618356595983` — `native-four-protocol-acceptance`.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
