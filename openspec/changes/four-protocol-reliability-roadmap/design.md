## Context

The original 22 transport findings were audited at 28783a7e1d48a0c192db4da06cf23b9d9a9d5637. Current main 605ae0be18dcbe1c55e3e7d8658131b2e0c201d3 integrates several repairs, while residual isolation, delivery, runtime acceptance, validation and authenticated topology defects remain. This behavioral epic coordinates their smallest coherent changes and a gated upgrade/feature path; it does not duplicate source-fixed work or revive cancelled external acceptance.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: deliver isolated reliable and upgradeable four-protocol connectivity with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- Use audit IDs A01-A22 only for traceability; all portfolio and execution IDs are allocated by taskctl. New changes remain backlog and all execution steps unchecked.
- A03,A07,A08,A09,A12,A14 have current source repairs and retain their existing owners. A16 has repaired cohort diagnostics plus residual backend/AWG health selection. A22 names remaining real transport proof rather than denying existing external liveness.
- Parent/blocked_by relationships define a source implementation DAG. Already integrated source fixes are related prerequisites, not artificial blockers merely because their original tasks remain in review. No existing evidence state is edited or weakened.
- Baseline fixes and real old-version native traffic precede every version upgrade. Exact candidate source/engine hashes and release status are refreshed at execution; tags, parsers or installed receipts alone cannot certify forwarding.
- One exact-source complete native/CI observation may satisfy multiple named linked requirements; preserve precise mappings and category boundaries instead of duplicating fleet rehearsals.
- No compatibility shim, arbitrary extra JSON, CDN baseline, admin API, unsupported fingerprint churn or S3/S4 guard relaxation enters this portfolio.
- Do not make protocol delivery depend on the separate vpnd Python migration. Both current and future convenience callers must obey the canonical Make/effective-client contracts when they integrate.
- Cancelled external acceptance remains dropped. Future provider, secret, client installation or production promotion requires current resource/action/cost/time authorization and a reviewable exact plan.

## Contracts and ownership

- Child OpenSpec changes and their exact owned runtime/schema/client/test scopes
- Existing reviewed remediation change records are read-only inherited evidence
- NEW audit-coverage.md and roadmap.md within this linked change; no separate process task
- Shared schemas, Makefile, CI selectors, snapshots and portfolio metadata have one serialized integration owner
- Dependencies: schema, boundary, runtime-transaction, awg-binding, awg-forwarding, xhttp-contract, topology-probes, drift, targets, integration, hysteria-upgrade, awg-upgrade, parser-upgrade, xhttp-features, hysteria-ech. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- Schema/client changes break ambiguous legacy contracts; every active repository caller and qualified consumer must move together.
- Native sockets/TUN, physical arm64 and staging are different boundaries; exact-source fixtures and read-only planning do not certify any of them.
- Shared-file overlap can corrupt otherwise independent work; implementation ownership and integration lanes must be assigned before parallel edits.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

Implement in the roadmap waves after separate authorization, keeping accepted old runtime/profile authority until the candidate passes its own required layer. Preserve every original source receipt and named gap. Stage optional candidate behavior only under reviewed technical cohorts and authorize production separately. Planning validation proves the artifacts are coherent, not that any new capability is implemented.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-PORTFOLIO-ISOLATION`: Run the child isolation, binding, schema and native-completion scenarios with exact runtime and client identities; link every A01-A22 row to a child or inherited owner.
- `REQ-PROTO-PORTFOLIO-LIFECYCLE`: Map real warm AWG, hopping, Xray rotation, nginx compensation/privacy and health topology scenarios to inherited and new linked owners.
- `REQ-PROTO-PORTFOLIO-EVOLUTION`: Require candidate-specific architecture/hash/advisory refresh, exact client parser/traffic, 48-hour staging where named and physical arm64 cases; retain PQE and nonzero S3/S4 HOLD.
- `REQ-PROTO-PORTFOLIO-EVIDENCE`: Validate complete audit coverage, DAG, source-fixed pointers and child evidence mappings; verify actual future source/native/client/staging results before feature completion.

## Validation commands

- `./taskctl graph --json`
- `env -u MAKEFILES -u MAKEFLAGS -u GNUMAKEFLAGS -u MFLAGS make task-check`
- `NEW make transport-native-acceptance on isolated Linux after implementation`
- `build-gate -- make check after implementation`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

## Canonical dependencies

- `SCT-1791617687019287` — `transport-input-semantics`.
- `SEC-1791617841911853` — `resolved-destination-boundary`.
- `ANS-1791617913525586` — `runtime-acceptance-transaction`.
- `SCR-1791618039091425` — `awg-device-binding`.
- `ANS-1791618048083304` — `awg-forwarding-dualstack`.
- `XRY-1791617955392712` — `xhttp-endpoint-contract`.
- `MON-1791618056169855` — `topology-authenticated-probes`.
- `SCR-1791618188806822` — `client-consumed-payload-identity`.
- `SCR-1791617975137354` — `reality-target-validation`.
- `TST-1791618356595983` — `native-four-protocol-acceptance`.
- `SCR-1791618064422507` — `hysteria-stable-upgrade`.
- `SCR-1791618073850409` — `awg-source-upgrade`.
- `TST-1791618376497512` — `stable-client-parser-upgrade`.
- `XRY-1791617991738391` — `xhttp-alternate-and-tuning`.
- `ANS-1791618083683925` — `hysteria-ech-profiles`.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.

## Audit and roadmap navigation

- [All 22 findings, inherited repairs and required acceptance](audit-coverage.md).
- [Prioritized DAG, release candidates and feature integration](roadmap.md).

These tables describe future execution and current source ownership, not new runtime evidence.
