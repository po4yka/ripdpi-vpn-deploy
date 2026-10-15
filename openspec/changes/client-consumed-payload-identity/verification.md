---
task_id: SCR-1791618188806822
change: client-consumed-payload-identity
commit_sha: a3a0763dd85321eb0474738108ab23415288ed8b
local: passed
local_evidence: 139 complete affected cases passed in 146.10s without selected skips; 279 transaction and 49 caller/gate cases also passed. Broad make check retained pre-fix failures and two timeouts; corrected cases and both original timeout cases passed on focused rerun. Full local make check is not claimed green.
remote_ci: passed
remote_ci_evidence: 'Exact implementation SHA: ci 38783529998, CodeQL 38783529682, markdown-link-check 38783529856 and claude-md-touch 38783529685 all completed successfully.'
dry_run: not_applicable
dry_run_evidence: source-only capability; no controller or provider execution in this task
staging: not_applicable
staging_evidence: isolated native source acceptance owns this change; fleet rehearsal requires separate authorization
live: not_applicable
live_evidence: no production rollout is part of this source task
client: passed
client_evidence: Real test-only SOPS/age issuance and refresh match canonical delivery; official sing-box parser passed. Native runtime job 116589727461 passed 138 runtime cases, two routed-edge cases and encrypted two-instance AWG TCP/UDP export/revocation/reissue acceptance.
artifact: passed
artifact_evidence: Schema, bundle, secrets coverage, encrypted synthetic fixture parity, snapshots and private marker/authority regressions passed. All implementation source checks passed at the recorded SHA.
---

# Verification

Evidence is pinned to the implementation commit above. The PR handoff changes
only task and verification metadata afterward. This is source acceptance using
synthetic encrypted authority and isolated native endpoints; it makes no fleet,
provider or production acceptance claim. Canonical predecessor edges remain open.

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
- Strict OpenSpec and task-history validation passed. Security review of the
  committed diff and working tree: **APPROVE**, no remaining findings.

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
