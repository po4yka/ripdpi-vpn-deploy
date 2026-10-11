## Context

The target validator describes ordinary curl with a Chrome User-Agent as browser ClientHello compatibility, manually accepts overly broad wildcard SAN suffixes, removes commas instead of splitting configured names and runs TLS work without deadlines. Target hygiene and filtered reachability are distinct, and owned self-steal targets need validation through their public service path rather than a remote sentinel's loopback.

Planning baseline: `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3` (2026-10-10). Revalidate source and current task ownership before implementation. This request creates plans only.

## Goals / Non-Goals

- Goal: make reality target validation bounded standards-correct and truthful with positive capability and meaningful negative, security, lifecycle and privacy tests.
- Non-goal: implementation in this session, provider mutation, production deployment, actual credentials, unrelated cleanup, compatibility shims or revival of cancelled acceptance.

## Decisions

- Use actual certificate hostname verification rather than hand-written suffix acceptance; wildcard scope is exactly one label and identity normalization is explicit.
- Name separators and duplicate handling are defined once; an empty or malformed name list refuses before network operations.
- Every subprocess and network stage has a deadline; the aggregate budget includes all addresses and names and cannot silently grow without bound.
- User-Agent selection is not TLS impersonation. A real browser-shaped client probe must have an exact pinned engine and an observed handshake, otherwise compatibility is unavailable rather than passed.
- Borrowed target hygiene and owned self-steal service-path checks are separate modes with explicit public endpoint/SNI ownership; a filtered sentinel never tests its own loopback as the server target.
- Validation never chooses a replacement target, edits secrets, issues certificates or deploys. Reports distinguish local hygiene, client compatibility and filtered-path evidence.

## Contracts and ownership

- scripts/validate-reality-target.sh
- scripts/monitor-reality-target.sh
- scripts/reality_target_monitor.py
- scripts/scan-reality-targets.sh
- scripts/CLAUDE.md
- docs/REALITY-TARGET-MONITORING.md
- ansible/roles/reality-self-steal/CLAUDE.md
- tests/unit/test_monitor_reality_target.py
- tests/unit/test_scan_reality_targets.py
- NEW: tests/unit/test_validate_reality_target.py
- Dependencies: None; may be implemented independently after baseline confirmation.. Exact IDs and hard edges are stored in portfolio frontmatter; related source-fixed tasks are traceability, not a new implementation blocker.
- Implementation starts only after separate authorization in a dedicated worktree; read nearest role/script/test guidance first.
- A single integration owner serializes schemas/examples, shared effective profile helpers, group variables, Makefile, CI selectors, snapshots and task metadata. Workers request shared-lane edits and preserve all concurrent work.
- Terraform owns provider objects, cloud-init owns bootstrap, Ansible owns runtime and SOPS owns private authority; no layer shortcut is introduced.

## Risks / Trade-offs

- Correct wildcard and separator validation can reject targets previously reported healthy by the flawed heuristic.
- Deadline policy must accommodate the full bounded name/address set while preventing one stalled process from holding the run indefinitely.
- Pinned browser-shaped client support may be unavailable in some environments; that absence must remain an explicit gap.
- A local successful handshake cannot establish transit survival or independently validate the service from another physical vantage.
- A passing renderer, fixture, socket or installed-version command cannot stand in for the requirement's named real runtime, authenticated traffic, physical device or rollback result.

## Migration Plan

Planning only. Implementation requires separate approval and updates all validation callers without retaining the false uTLS label as a compatibility alias. Existing TLS concurrency and target monitoring authority remain preserved. No changes to active targets or private material follow from this plan. A future target promotion separately requires exact owned identity, real supported-client handshake, approved filtered-vantage evidence and authenticated previous-target rollback; current PQE HOLD and stable runtime pins remain unchanged.

Implementation order follows the dependency DAG. Run each complete affected test suite; use `build-gate` once around heavy top-level builds and never bypass pinned tools or safety hooks. Archive/closure remains unavailable while any requirement or required evidence category is unresolved.

## Acceptance tests

- `REQ-PROTO-RTV-IDENTITY`: NEW test_validate_reality_target.py with controlled exact wildcard deep-label mixed comma/space duplicate and empty-name cases.
- `REQ-PROTO-RTV-DEADLINES`: NEW real subprocess deadline and child-cleanup tests for DNS TLS HTTP and multi-name aggregate work; retain current monitor state tests.
- `REQ-PROTO-RTV-CLAIMS`: NEW truthful report/available-client tests; inspect real handshake execution boundary rather than using a User-Agent assertion as proof.
- `REQ-PROTO-RTV-OWNERSHIP`: NEW owned public-path/loopback distinction and no-mutation/privacy regressions, reusing current self-steal transaction fixtures for accepted authority preservation.

## Validation commands

- `mise exec -- python3 -m pytest tests/unit/test_monitor_reality_target.py tests/unit/test_scan_reality_targets.py`
- `make shellcheck`
- `build-gate -- make check`
- `NEW make test-reality-target-validation — Run controlled credential-free real TLS identity client-claim and deadline tests; do not resolve production private targets.`

Commands marked NEW are implementation deliverables and must exist, execute complete cases and fail on selected skips before acceptance. They are not commands run during planning. No credentialed recipe is authorized merely by being listed here.

## Canonical dependencies

- No new implementation prerequisite.

These are canonical `blocked_by` edges; child requirements can be prepared and characterized before a blocker closes, but promotion/acceptance follows the graph. Existing integrated review records are preserved as related evidence and do not imply a new fleet acceptance.
