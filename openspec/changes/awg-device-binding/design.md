## Context

The deployed role treats a nonempty instance collection as authoritative, while enrollment and public emitters still write or read the legacy top-level peer collection and fixed address pool. Issuance can therefore succeed with a peer absent from the deployed server, emit the wrong endpoint and parameters, or silently omit an enabled AWG profile.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: deliver authoritative amneziawg device enrollment and client bindings with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- The schema remediation owns baseline AWG relationship validation. Reuse that completed contract rather than implementing duplicate preflight rules; this change owns authoritative device-binding and enrollment consumer integration.
- Binding identity comprises technical host identity, effective instance name and device name; select it explicitly when more than one instance can match. Every selected result must be unique.
- Replace the conflicting published source contract and update every repository caller. Do not retain top-level legacy peer and instance code paths solely for backward compatibility.
- Enrollment allocates a host identity in the effective pool and excludes server, reserved and already assigned addresses. Routed peer prefixes are a separate explicit contract and are not silently treated as device addresses.
- Use one semantic validator for header distinctness, ordered junk bounds, instance names, peer prefix collisions and exact key shape; preserve the existing S3/S4 zero policy.
- Private recovery material stays in encrypted storage; normalization, handler loops, error diagnostics and exports cannot expose keys or PSKs.
- A qualified consumer task and federation validation are mandatory before changing a cross-repository bundle contract; no consumer task ID is invented by this preparation.
- Current source already repairs runtime notifications and owned instance retirement. Preserve their existing requirements and receipts; do not reimplement or falsely close them.
- Planning approval does not authorize implementation, credential issuance, PR publication or deployment.

## Contracts and ownership

- scripts/new-client.sh
- scripts/rotate-secrets.sh
- scripts/emit-awg.sh
- scripts/emit-bundle.sh
- scripts/liveness_profiles.py
- scripts/validate-secrets.py
- secrets/schema.json
- secrets/prod.secrets.example.yaml
- ansible/roles/amneziawg/tasks/instances.yml
- scripts/ripdpi_cohort_fingerprint.py
- contract/cohort-fingerprint.golden.json
- contract/ripdpi-bundle.schema.json
- tests/unit/test_emit_bundle_host_selection.py
- tests/unit/test_bootstrap_awg_handoff.py
- tests/unit/test_secrets_schema.py
- docs/AWG-COHORTS.md
- docs/RIPDPI-BUNDLE.md
- scripts/CLAUDE.md
- ansible/roles/amneziawg/CLAUDE.md
- Dependencies: schema. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- Changing binding selection can invalidate previously issued profiles; the migration must explicitly identify the contract break and regenerate only authorized device material.
- Address allocation and revocation errors can remove a different device or cause routing collisions; isolated positive and negative tests precede source integration.
- A shared resolver must not turn secret-bearing normalization into callback output or copy server private material into recipient artifacts.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

After separate implementation approval, inventory all repository consumers and replace the ambiguous binding contract coherently. Validate existing encrypted documents privately without loading plaintext into session logs. Reissue affected recipient profiles only under separate credential authorization. Existing source review receipts remain unchanged; no remote retirement or live acceptance is implied.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-AWG-BIND`: Extend test_emit_bundle_host_selection and add canonical binding tests comparing real role renders, standalone emitter, RIPDPI bundle and liveness resolver; inspect only synthetic public summaries.
- `REQ-PROTO-AWG-ENROLL`: Exercise real SOPS/age temporary encrypted documents and actual enrollment/revocation scripts, including distinct public keys, pool limits, lock behavior and interrupted publication; fixtures are not live delivery proof.
- `REQ-PROTO-AWG-PARITY`: Add shared semantic boundary tests, fingerprint golden cases and an exact-binary Linux TUN positive/negative fixture; retain arm64 floor tests.
- `REQ-PROTO-AWG-PRIVATE`: Run verbose-callback secret-leak regressions, unsafe output-path tests, migration fixtures and an all-caller discovery assertion; use synthetic secret markers only.

## Validation commands

- `mise exec -- python3 -m pytest -q tests/unit/test_emit_bundle_host_selection.py tests/unit/test_bootstrap_awg_handoff.py tests/unit/test_secrets_schema.py`
- `make snapshot-check`
- `make task-check`
- `build-gate -- make check`
- `Existing when the qualified peer checkout is available: make task-federation PEER_ROOT=<RIPDPI-checkout>`
- `NEW make test-awg-device-binding-runtime; implementation must add exact-binary two-instance Linux TUN enrollment export and revocation coverage to the canonical native lane`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

## Canonical dependencies

- `SCT-1791617687019287` — `transport-input-semantics`.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
