---
task_id: SCR-1791618039091425
change: awg-device-binding
commit_sha: 923304729f6bdd32edce6a9b6ceada1d51c7d011
local: required
local_evidence: "61 encrypted transaction tests passed with actual SOPS and age; exact-main portable/native suites passed. Complete local make check pending."
remote_ci: passed
remote_ci_evidence: "Exact main CI 38759230876 and CodeQL 38759230898 succeeded; native integration 138, XHTTP 2, AWG binding 1 and runtime acceptance 4 cases passed."
dry_run: not_applicable
dry_run_evidence: source capability uses isolated native proof; real inventory/controller rehearsal needs separate authorization
staging: not_applicable
staging_evidence: source contract uses isolated native acceptance; actual fleet rehearsal is separately authorized
live: not_applicable
live_evidence: no production rollout belongs to this source or disabled-default candidate task
client: passed
client_evidence: exact-source hosted native lanes passed 138 baseline cases, two endpoint cases, the AWG binding case and four runtime acceptance cases; real local QR encode/decode passed
artifact: passed
artifact_evidence: real SOPS/age issuance and qrencode/zbar roundtrip passed; private cleanup, committed-error URI retention and credential exclusion passed
---



# Verification

## Requirement evidence

Initial implementation source `7656701b080753f5e84c8fce74ab080441d13be6` passed the gates documented below. Review follow-up source `447b8db214f9c31601675a4d6dd9668ac1c05bf2` passed the additional gates recorded below. Acceptance covers source and isolated native clients; no real inventory, private operator migration or deployment is claimed.

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-AWG-BIND | SCR-1791618044456243 | test_awg_device_binding.py and test_emit_bundle_host_selection.py verify shared instance selection; the actual native CLI compares role rendering, standalone emission, RIPDPI bundle and liveness fields. | passed |
| REQ-PROTO-AWG-BIND | SCR-1791618045793096 | test_awg_device_binding.py and test_emit_bundle_host_selection.py verify shared instance selection; the actual native CLI compares role rendering, standalone emission, RIPDPI bundle and liveness fields. | passed |
| REQ-PROTO-AWG-BIND | SCR-1791618046582572 | test_awg_device_binding.py and test_emit_bundle_host_selection.py verify shared instance selection; the actual native CLI compares role rendering, standalone emission, RIPDPI bundle and liveness fields. | passed |
| REQ-PROTO-AWG-ENROLL | SCR-1791618045140064 | test_awg_encrypted_transactions.py and new_client_atomic.bats exercise real SOPS/age issuance, distinct keys, selected pools and revocation, locking, failed encryption and preservation; the native case proves authenticated device traffic. | passed |
| REQ-PROTO-AWG-ENROLL | SCR-1791618046582572 | test_awg_encrypted_transactions.py and new_client_atomic.bats exercise real SOPS/age issuance, distinct keys, selected pools and revocation, locking, failed encryption and preservation; the native case proves authenticated device traffic. | passed |
| REQ-PROTO-AWG-PARITY | SCR-1791618044456243 | Shared transport semantic, fingerprint and arm64 floor tests pass; test_awg_device_binding_native.py consumes exact AWG binaries and canonical selected exports for TCP/UDP and wrong-key/header failures. | passed |
| REQ-PROTO-AWG-PARITY | SCR-1791618045793096 | Shared transport semantic, fingerprint and arm64 floor tests pass; test_awg_device_binding_native.py consumes exact AWG binaries and canonical selected exports for TCP/UDP and wrong-key/header failures. | passed |
| REQ-PROTO-AWG-PARITY | SCR-1791618046582572 | Shared transport semantic, fingerprint and arm64 floor tests pass; test_awg_device_binding_native.py consumes exact AWG binaries and canonical selected exports for TCP/UDP and wrong-key/header failures. | passed |
| REQ-PROTO-AWG-PRIVATE | SCR-1791618044456243 | Real encrypted transaction and private CLI artifact tests reject unsafe authority, preserve prior artifacts/ciphertext, retain committed recipient material after sync/close failures and exclude URI credentials from metadata; inherited callback privacy and all-caller checks pass. | passed |
| REQ-PROTO-AWG-PRIVATE | SCR-1791618045140064 | Real encrypted transaction and private CLI artifact tests reject unsafe authority, preserve prior artifacts/ciphertext, retain committed recipient material after sync/close failures and exclude URI credentials from metadata; inherited callback privacy and all-caller checks pass. | passed |
| REQ-PROTO-AWG-PRIVATE | SCR-1791618046582572 | Real encrypted transaction and private CLI artifact tests reject unsafe authority, preserve prior artifacts/ciphertext, retain committed recipient material after sync/close failures and exclude URI credentials from metadata; inherited callback privacy and all-caller checks pass. | passed |

## Initial implementation checks

- `make check` passed on the final implementation tree: 6,859 portable tests and 22 subtests, all 59 shell cases, all 303 CLI cases, complete CLI transfer/parity, Terraform mock/policy checks, lint, schemas and all 163 snapshots. The local environment used Python 3.12 and SOPS 3.13.2; hosted encryption used checksum-verified SOPS 3.13.3.
- The final changed-path regression suite passed 179 tests; all 21 encrypted transaction cases and the complete three-case CI tooling contract passed. The Bats lane now installs the same pinned Python dependencies and checksum-verified SOPS rather than relying on a fake encryption success path.
- Hosted CI run 38600990479 and CodeQL run 38600990502 succeeded on `7656701b080753f5e84c8fce74ab080441d13be6`; all 93 successful contexts were terminal and the optional Trivy context was neutral. The source privacy finding was fixed by private no-clobber URI output, not suppressed.
- The exact-source native integration passed 138 baseline cases in 1,005.96 seconds, two endpoint cases in 149.65 seconds, and the new AWG binding case in 9.29 seconds. Actual SOPS CLI enrollment/revocation, both canonical emitters, bundle validation, role/liveness parity, two-instance TCP/UDP traffic, wrong-key/header refusal and isolated revocation all passed. The separate four-case native transport acceptance passed in 1,502.29 seconds with owned environment retirement.
- An additional isolated local ARM64 AWG case passed in 8.60 seconds using the same exact AWG source commits; its owned container and staging copy were retired. Local emulated Molecule preparation could not establish its temporary-directory prerequisite; the complete hosted role and full-stack lanes subsequently passed on the recorded source.
- Independent spec and standards/security reviews approved the final implementation with no remaining actionable findings. Normal commit hooks passed; no gate was bypassed. No deployment, real credential issuance, physical-device acceptance or live fleet claim belongs to this source task.
- The public bundle schema and cohort fingerprint algorithm are unchanged. Conditional consumer federation could not run because available client checkouts lack `tools/tasking/project.json`; no new cross-repository wire contract is introduced.

## Review follow-up

PR #298 identified the URI QR caller missing private output, dash-prefixed names
being interpreted as options, null bindings retaining live device peers, stale
secrets-shape documentation, and a mixed-import CodeQL note. All five findings
are fixed in source `447b8db214f9c31601675a4d6dd9668ac1c05bf2`.

- The affected suite passed 206 tests. Additional URI boundary verification passed
  all six script/Make cases after the equivalent scheme-pattern adjustment.
- Real SOPS 3.13.3/age issuance, qrencode 4.1.1 PNG creation and zbar 0.23.93
  decoding passed in an owned isolated ARM64 container. Private cleanup,
  credential exclusion and retained private URI recovery after a committed
  rendering failure passed. The container and its anonymous volumes were retired.
- Local `make check` passed 6,872 portable tests and 22 subtests, 59 Bats cases,
  163 snapshots, schemas, lint and Terraform/policy checks before failing one
  unchanged one-second CLI lifecycle case. An isolated lifecycle diagnostic
  passed that case but failed a different invoke assertion. The Mac load average
  exceeded 200 during diagnosis. A complete clean-Make-environment
  `make vpnd-test vpnd-parity-check` rerun then passed all 303 CLI cases in
  76.66 seconds and all 206 baseline-function mappings. The initial aggregate
  command is recorded as failed; no test or timeout was weakened.
- Exact-source CI run 38686110763 and CodeQL run 38686110633 completed with
  93 successful checks and one optional neutral Trivy context. Three jobs first
  failed before checkout while GitHub downloaded the pinned setup-go action;
  rerunning only failed jobs passed without changing its verified upstream pin.
- Exact-source native integration passed 138 baseline cases in 994.81 seconds,
  two endpoint cases in 151.23 seconds and the AWG binding case in 9.83 seconds.
  Native transport acceptance passed four cases in 1,556.34 seconds.
- The mixed-import CodeQL finding automatically resolved. Security review of the
  follow-up is APPROVE: no actionable finding remains in the diff; real operator
  credentials, deployment and physical-device acceptance remain outside scope.
  All applicable normal commit hooks passed without a bypass.

## Additional review follow-up

Five further findings require persisted registry authority, global device-name
uniqueness, consistent interface-name grammar, AWG Make defaults and AWG-only
reissuance after revocation. Final acceptance is reopened for their fixes and
exact-source verification; earlier results above remain historical evidence.

Four further reviewed boundaries remain pending final gates: canonical lowercase
host names, complete first-token AWG defaults, success-only encrypted Make audit
and nonblocking unsafe-source refusal. Their regressions reproduced the failures
before the fixes. Earlier accepted commits above are historical evidence.

The final registry follow-up also rejects device peers without persisted registry
authority, while exempting routed peers. Shared encrypted/native fixtures now
carry actual matching recovery keys and complete authority for all device peers.
The earlier in-flight local suite collected its fixtures before this rule;
complete final-source validation must run again with the updated fixtures.

Final closeout also shares registry admission between preflight and mutations,
rejects unsupported policy fields, scopes de-onboarding to the verified host,
and records required AWG delivery selection independently of credential binding.
The closeout worktree preserves the unchanged baseline while final gates run.

## Integrated source verification (2026-10-15)

Exact main CI 38759230876 and CodeQL 38759230898 succeeded; native integration 138, XHTTP 2, AWG binding 1 and runtime acceptance 4 cases passed. Source is `923304729f6bdd32edce6a9b6ceada1d51c7d011`; hosted logs were inspected directly. 61 encrypted transaction tests passed with actual SOPS and age; exact-main portable/native suites passed. Complete local make check pending. No external infrastructure or real notification action occurred.
