---
task_id: SCR-1791618188806822
change: client-consumed-payload-identity
commit_sha: null
local: passed
local_evidence: 'PR review follow-up: complete affected suites passed 251 cases in 111.02s and 144 cases in 57.25s, without selected skips. Task contracts and strict OpenSpec validation passed. Full make check is queued behind the shared machine gate.'
remote_ci: required
remote_ci_evidence: 'PR #302 review follow-up: partial-publication tracking and interruption regressions require fresh source validation; baseline evidence below belongs to a3a0763dd85321eb0474738108ab23415288ed8b.'
dry_run: not_applicable
dry_run_evidence: source-only capability; no controller or provider execution in this task
staging: not_applicable
staging_evidence: isolated native source acceptance owns this change; fleet rehearsal requires separate authorization
live: not_applicable
live_evidence: no production rollout is part of this source task
client: required
client_evidence: 'PR #302 review follow-up: partial-publication tracking and interruption regressions require fresh source validation; baseline evidence below belongs to a3a0763dd85321eb0474738108ab23415288ed8b.'
artifact: required
artifact_evidence: 'PR #302 review follow-up: partial-publication tracking and interruption regressions require fresh source validation; baseline evidence below belongs to a3a0763dd85321eb0474738108ab23415288ed8b.'
---

# Verification

The baseline evidence below is pinned to implementation commit
`a3a0763dd85321eb0474738108ab23415288ed8b`. PR review follow-up validation
is pending for partial external publication and interruption handling. This is source acceptance using
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
validation passed. Exact committed-source CI remains required.
