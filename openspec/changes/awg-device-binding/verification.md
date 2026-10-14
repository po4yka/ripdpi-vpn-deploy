---
task_id: SCR-1791618039091425
change: awg-device-binding
commit_sha: 7656701b080753f5e84c8fce74ab080441d13be6
local: passed
local_evidence: 'make check passed: 6859 portable tests, 22 subtests, 59 shell cases, 303 CLI cases; 163 snapshots and pinned client parsers passed'
remote_ci: passed
remote_ci_evidence: 'CI run 38600990479 and CodeQL run 38600990502 succeeded on the recorded source: 93 successful checks and one optional neutral check; 138 baseline native, two endpoint native, one AWG binding and four runtime acceptance cases passed'
dry_run: not_applicable
dry_run_evidence: source capability uses isolated native proof; real inventory/controller rehearsal needs separate authorization
staging: not_applicable
staging_evidence: source contract uses isolated native acceptance; actual fleet rehearsal is separately authorized
live: not_applicable
live_evidence: no production rollout belongs to this source or disabled-default candidate task
client: passed
client_evidence: Exact pinned AWG Go v0.2.12 and tools v1.0.20241018 completed selected canonical CLI exports, two-instance authenticated TCP/UDP, wrong-key/header rejection and isolated revocation on hosted AMD64; additional local ARM64 native acceptance passed
artifact: passed
artifact_evidence: Private recipient publication, original ciphertext retention, safe post-commit uncertainty and metadata-only URI output passed real SOPS/age regressions; 163 snapshots match
---


# Verification

## Requirement evidence

The recorded source passed the complete local gate, independent spec and standards/security reviews, and terminal exact-source hosted checks. Acceptance covers source and isolated native clients; no real inventory, private operator migration or deployment is claimed.

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

## Observed checks

- `make check` passed on the final implementation tree: 6,859 portable tests and 22 subtests, all 59 shell cases, all 303 CLI cases, complete CLI transfer/parity, Terraform mock/policy checks, lint, schemas and all 163 snapshots. The local environment used Python 3.12 and SOPS 3.13.2; hosted encryption used checksum-verified SOPS 3.13.3.
- The final changed-path regression suite passed 179 tests; all 21 encrypted transaction cases and the complete three-case CI tooling contract passed. The Bats lane now installs the same pinned Python dependencies and checksum-verified SOPS rather than relying on a fake encryption success path.
- Hosted CI run 38600990479 and CodeQL run 38600990502 succeeded on `7656701b080753f5e84c8fce74ab080441d13be6`; all 93 successful contexts were terminal and the optional Trivy context was neutral. The source privacy finding was fixed by private no-clobber URI output, not suppressed.
- The exact-source native integration passed 138 baseline cases in 1,005.96 seconds, two endpoint cases in 149.65 seconds, and the new AWG binding case in 9.29 seconds. Actual SOPS CLI enrollment/revocation, both canonical emitters, bundle validation, role/liveness parity, two-instance TCP/UDP traffic, wrong-key/header refusal and isolated revocation all passed. The separate four-case native transport acceptance passed in 1,502.29 seconds with owned environment retirement.
- An additional isolated local ARM64 AWG case passed in 8.60 seconds using the same exact AWG source commits; its owned container and staging copy were retired. Local emulated Molecule preparation could not establish its temporary-directory prerequisite; the complete hosted role and full-stack lanes subsequently passed on the recorded source.
- Independent spec and standards/security reviews approved the final implementation with no remaining actionable findings. Normal commit hooks passed; no gate was bypassed. No deployment, real credential issuance, physical-device acceptance or live fleet claim belongs to this source task.
- The public bundle schema and cohort fingerprint algorithm are unchanged. Conditional consumer federation could not run because available client checkouts lack `tools/tasking/project.json`; no new cross-repository wire contract is introduced.
