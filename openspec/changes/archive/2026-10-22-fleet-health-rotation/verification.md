---
task_id: OPS-1792654666090980
change: fleet-health-rotation
commit_sha: 37939d5a412b11375b71172e7fbf1bad9d73bb5a
local: passed
local_evidence: Complete build-gated make check passed on the fleet source with 9387 portable tests, 45 subtests, 379 vpnd tests and 70 Bats tests; all remaining credential-free gates passed. After integrating main, the complete six affected suites passed 224 tests on d808f5ee, whose source tree matches integrated main 37939d5a. Task contracts and diff whitespace checks passed.
remote_ci: passed
remote_ci_evidence: All nine protected-main checks passed on exact integrated source 37939d5a412b11375b71172e7fbf1bad9d73bb5a. Main CI run 39761736896 and CodeQL run 39761737020 completed successfully, including every native runtime, Molecule, portable, lint and policy gate.
dry_run: passed
dry_run_evidence: Complete fleet_rotate_dryrun.bats (11 passed), input_validation.bats (6 passed), and isolated Python dry-run regression; no state, liveness read or host access.
staging: not_applicable
staging_evidence: Source-only controller fixes; no staging infrastructure operation is authorized or required.
live: not_applicable
live_evidence: No provider or live host mutation; runtime reachability is not claimed.
client: not_applicable
client_evidence: No recipient contract or client implementation changes.
artifact: not_applicable
artifact_evidence: No separately distributed artifact; reviewed repository source is the deliverable.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-FLEET-SSH | OPS-1792654871067546 | Status/inspection unit regressions and independent review | passed |
| REQ-FLEET-STATUS | OPS-1792654871067546 | Successful, failed, absent, future and stale watchdog regressions | passed |
| REQ-FLEET-MIN-ACTIVE | OPS-1792654872580225 | Authenticated survivor and stale/wrong-target refusal tests | passed |
| REQ-FLEET-RESUME | OPS-1792654873965490 | Positive resume and changed/malformed/legacy plan-state tests | passed |
| REQ-FLEET-JOURNAL | OPS-1792654873965490 | Concurrent/interrupted/unsafe-state and dry-run regressions | passed |

## Acceptance scope

Focused and complete local gates plus required protected PR/main checks passed.
Simulated external boundaries prove controller decisions only; they
do not establish live client-path reachability or deployment acceptance.

## Observed controller evidence

- Full status and inspection unit files: 79 passed, including the final unrelated-CWD regression; independently repeated.
- Full rotation unit file: 43 passed, repeated independently by the reviewer.
- Complete affected Bats files: 11 fleet-rotation and 6 input-validation cases passed.
- Operator-path integration: 26 tests passed; audit hook regression corrected and
  full status/inspection/audit bundle passed 81 tests.
- `make task-check shellcheck` and `git diff --check` passed.
- Complete `make check` passed: 9387 portable tests, 45 subtests, 379 vpnd
  tests, 70 Bats tests, Terraform mock and policy tests, production Ansible
  lint, schema/render/snapshot checks, and pinned client-parser validation.
- After integrating the updated base, the complete hardware-age migration,
  subscription expiry, transport-runtime acceptance, status, inspection and
  rotation suites passed 224 tests on the integrated source tree.
- PR 356 merged as `37939d5a412b11375b71172e7fbf1bad9d73bb5a` after all nine
  protected checks passed on `d808f5ee3737efe54c25fc49291b0c945c4c06f5`;
  CI run 39754041099 and CodeQL run 39754041213 both succeeded.
- Legacy duplicate-key rotation plan exits zero; the new wrapper refuses it.
- Independent review found and resolved inherited dry-run completion, degraded
  AWG family acceptance, duplicate source/survivor identity and uncertain journal
  publication. No remaining scoped security findings; all required gates passed.
