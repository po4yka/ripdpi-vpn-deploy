---
task_id: SCR-1791618188806822
change: client-consumed-payload-identity
commit_sha: null
local: passed
local_evidence: 'Complete review-follow-up suites: 251 passed in 111.02s and 144 passed in 57.25s, without selected skips. Task/OpenSpec validation and all commit hooks passed. Full make check did not execute: its queued run was stopped after more than 12 minutes waiting for the shared build gate.'
remote_ci: "not_applicable"
remote_ci_evidence: "Owner selected local completion on 2026-10-16; complete local source gates are required. Automatic PR checks remain separate review evidence."
dry_run: not_applicable
dry_run_evidence: source-only capability; no controller or provider execution in this task
staging: "not_applicable"
staging_evidence: "Owner removed staging soak on 2026-10-16; isolated local runtime acceptance is required instead."
live: not_applicable
live_evidence: no production rollout is part of this source task
client: "not_applicable"
client_evidence: "Owner removed external and device acceptance on 2026-10-16; real local protocol engines remain required under local evidence."
artifact: passed
artifact_evidence: 'All 31 canonical contract files match RIPDPI origin/main c843303bc. Regenerated the combined encrypted synthetic fixture; complete 399-case drift, transaction, retirement, binding, dual-stack, bundle and SOPS suites passed.'
---

# Verification

## Local completion scope (2026-10-16)

The owner authorizes full local implementation and removes staging soak, external recipient, Android emulator and physical-device acceptance from this change. Completion requires actual pinned local engines, isolated Linux systemd/network namespaces/TUN where applicable, authenticated positive and rejection traffic, compensation, privacy and complete source checks. Synthetic credentials are test inputs; mocks, render-only checks and refusal-only results cannot replace runnable behavior. External devices, provider actions, production rollout and promotion are outside acceptance. Earlier observations below retain their original source and limitations; removed external gates are excluded by this scope revision, never recorded as passed.


The baseline evidence below is pinned to implementation commit
`a3a0763dd85321eb0474738108ab23415288ed8b`. The review fixes below are pinned to
`13ccd1590ae04f9d3eb6117770386e77e9cd2dff`; their affected suites and CodeQL
passed. Complete source acceptance remains blocked by cross-repository contract drift. This is source acceptance using
synthetic encrypted authority and isolated native endpoints; it makes no fleet,
provider or production acceptance claim. Canonical predecessor references are retained; current main owns their accepted terminal state.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DRIFT-CHECK | SCR-1791618347514825 | Shared renderer with real SOPS/age covers credentials, endpoints, bindings, parameters, expiry and unrelated edits. A coherent enrolled-peer key rotation reports stale even when placeholder-based exported JSON stays identical. | passed |
| REQ-PROTO-IDENTITY-ISSUANCE | SCR-1791618349798761 | Issuance/refresh compares exact canonical delivery, persisted per-host sources and AWG selection. Fixed-clock unchanged refresh republishes; failed candidate encryption retains ciphertext and prior delivered bytes. | passed |
| REQ-PROTO-IDENTITY-PRIVACY | SCR-1791618352269556 | Marker checks cover child argv/environment, audit and diagnostics. Unsafe private file modes/types, malformed consumed authority and real child deadlines refuse categorically. | passed |
| REQ-PROTO-IDENTITY-AUTHORITY | SCR-1791618352269556 | Real encrypted authority creation, loss, rotation, malformed key/version, mismatched generation and ciphertext-only re-encryption. Inspection creates no authority and retains ciphertext. | passed |

## Observed checks

- Complete local affected suites: `test_client_drift.py`,
  `test_client_registry.py`, `test_subscription_expiry.py`,
  `test_emit_singbox_roundtrip.py` and `test_emit_bundle_host_selection.py`,
  with `--fail-on-skip`: **139 passed** in 146.10 seconds.
- Broader transaction/issuance suites: **279 passed**; caller/gate suites:
  **49 passed**; registry/QR contract run: **45 passed**. Official sing-box
  parsing, schema/bundle validation, secrets coverage, snapshots and encrypted
  synthetic fixture parity passed.
- `build-gate -- make check` was run. Its broad retry completed **7207 passing
  cases and 22 subtests**, then reported six pre-fix failures and two unchanged
  Ansible timeouts (30 and 45 seconds). The six corrected cases passed in
  affected reruns; both original timeout cases passed in **5.18 seconds** at
  their original bounds. No assertion or timeout was relaxed. The duplicate
  local Bats/vpnd remainder was stopped before execution after waiting more
  than 25 minutes for the machine gate; its hosted counterparts passed.
- The complete hosted CI workflow, CodeQL, Markdown links and instruction-doc
  checks passed on the exact implementation SHA. Native runtime integration
  passed **138 + 2 + 1 cases**, including real encrypted two-instance AWG
  authenticated TCP/UDP, wrong-key/header rejection, isolated revocation and
  fresh-key reissue. Native transport acceptance also passed.
- Strict OpenSpec and task-history validation passed. Baseline security review was **APPROVE**; the review follow-up requires fresh validation.

## Migration and limits

Old source/output identities remain unknown until explicit authorized
redelivery; inspection neither upgrades records nor generates replacement
keys. The private identity binds the actual enrolled peer public key even
when a recipient export contains a private-key placeholder. Explicit cohorts
consume only the endpoint and do not require an unused hostname lookup.

Candidate verification precedes remote writes. Local SOPS and remote delivery
cannot form one distributed atomic commit; reconcile both after interrupted
publication before retrying. No merge, deployment or task closure is implied
by this review handoff.

## PR review follow-up

- Removed the unused test import reported by CodeQL.
- Reproduced remote metadata publication followed by an ordinary exit-2 error.
  External publication is now marked before its first mutating SSH attempt.
  A failed reply, payload write, local replace/sync or interruption requires
  reconciliation of remote delivery and encrypted registry before retrying.
- All callback consumers use the explicit marker contract; local recipient
  validation remains separate from external mutation.
- Current main was merged without rewriting published history. Its task
  acceptance and instruction changes are preserved.

Complete review-follow-up suites passed **395 cases** without selected skips:
251 drift/encrypted-transaction/retirement cases and 144 registry, expiry,
emitter, audit and Make caller cases. Task contracts and strict OpenSpec
validation passed. The complete source gate remains open because contract-sync fails independently of these changes.

Both PR review threads were resolved after the code was pushed, the complete
affected suites passed and CodeQL completed successfully. Current main was
merged, and the PR is mergeable. Its source-gate checklist step remains open.

### Remaining source gate

The failed contract-sync job compares this repository's unchanged canonical
contract with RIPDPI's default-branch vendored resources. The peer schema now
requires exactly one IPv4 /32 and one IPv6 /128 address, and an MTU between
1280 and 1420; this repository still exports the canonical single peer address.
Eight vendored files differ. A separate cross-repository transport change must
align schema, export behavior and client acceptance before this gate can pass.
The local full-gate attempt was stopped while still queued behind the machine
gate; no local full-gate success is claimed.

## Coordinated contract integration (2026-10-16)

The owner authorized resolving downstream drift and completing PR #302 CI.
Integrated PR #304 producer `edd61bdcd9d800a1d169cadaa60aeb64de0381a0`,
including typed dual-family device claims, MTU resolution, runtime forwarding
and compensation, exporter and schema. Its client companion is merged at
`c843303bc`; all 31 contract files match byte-for-byte. Neither producer PR
nor this PR has been merged to main by this integration.

The shared in-memory renderer already calls the canonical AWG exporter. New
real encrypted regressions require both device addresses and MTU in the
published schema, stale after either address or MTU changes, and read-only
unknown after missing-family, scalar-address or out-of-bounds MTU inputs.
Complete affected suites passed 399 cases without selected skips. Exact
integrated-source CI and the queued complete local gate remain pending.
The earlier failed contract-sync evidence above is historical.
