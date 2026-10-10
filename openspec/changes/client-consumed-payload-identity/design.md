## Context

client-drift.py compares source and selected Terraform output hashes but does not consume the SOPS-owned material that can change a delivered payload. The existing main specification already requires re-rendering current inputs.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: detect client payload drift from every consumed private input with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- Use one deterministic payload materializer in memory; preserve original format, host, cohort and explicit AWG binding. Read only validated private inputs at authorized execution time.
- Store a versioned keyed digest of the canonical selected-device consumed payload inside the encrypted registry, with a separately generated private digest authority. Do not publish raw secret hashes or plaintext material; re-encryption and ignored metadata changes do not alter identity.
- Missing old identity becomes unknown until an explicit authorized redelivery computes the new identity; never infer current or add a legacy identity comparison.
- Keep diagnostic output categorical and preserve existing per-device locks, atomic encrypted writes and transient cleanup. Do not make this change depend on the unrelated vpnd Python migration.
- Use a versioned HMAC-SHA256 construction with 256-bit private authority in a typed SOPS client-delivery-identity section. Domain-separate by format, device, exact bindings and identity version; record a nonsecret authority generation inside the encrypted registry. Only an explicitly authorized issuance/rotation transaction may create or rotate authority. Inspection with missing, malformed, lost, unavailable or mismatched-generation authority returns unknown without creating keys or comparing incomparable digests. Ciphertext-only re-encryption retains the authority generation and verdict.

## Contracts and ownership

- scripts/client-drift.py
- scripts/issue-sub-token.sh
- scripts/emit-bundle.sh
- scripts/emit-awg.sh
- scripts/emit-singbox.sh
- secrets/schema.json
- tests/unit/test_client_drift.py
- tests/unit/test_client_registry.py
- openspec/specs/clients/config-registry/spec.md
- Dependencies: awg-binding, xhttp-contract. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- A published contract change may reject previously accepted inputs; update all consumers atomically and test unchanged supported inputs.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

BREAKING: old source/output-only identity is not accepted as proof of current payload. Authorized redelivery establishes the new encrypted record; report unknown meanwhile. Update both current CLI callers and any subsequently migrated Python CLI consumers at their integration boundary.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-DRIFT-CHECK`: Extend test_client_drift.py with actual canonical materializer runs and real test-only SOPS encryption, not only injected hash equality.
- `REQ-PROTO-IDENTITY-ISSUANCE`: Run real local issuance/refresh with test-only SOPS and compare private canonical outputs in owned temporary storage.
- `REQ-PROTO-IDENTITY-PRIVACY`: Failure injection, stdout/stderr/process-metadata scan and owner/type/mode tests; document exact digest authority lifecycle.
- `REQ-PROTO-IDENTITY-AUTHORITY`: Actual test-only encrypted authority creation at authorized issuance; loss rotation malformed-generation and ciphertext-only re-encryption tests with marker-free diagnostics.

## Validation commands

- `mise exec -- python3 -m pytest -q tests/unit/test_client_drift.py tests/unit/test_client_registry.py`
- `build-gate -- make check`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

## Canonical dependencies

- `SCR-1791618039091425` — `awg-device-binding`.
- `XRY-1791617955392712` — `xhttp-endpoint-contract`.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
