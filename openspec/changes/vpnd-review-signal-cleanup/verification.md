---
task_id: SEC-1792842686096891
change: vpnd-review-signal-cleanup
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: Only isolated CLI fixtures are used; no real Ansible dry-run is authorized or needed.
staging: not_applicable
staging_evidence: This local CLI fix does not provision or change a staging host.
live: not_applicable
live_evidence: No live provider, host, credential or deployment action is in scope.
client: not_applicable
client_evidence: No VPN client or physical device behavior changes.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DRF-REVIEW | SEC-1792842915023775 | Actual launcher PTY, worker-targeted signals, terminal authority and signal/answer ordering | Required |
| REQ-PYSAFE-CLEANUP | SEC-1792842915762104 | Cleanup once, plaintext removal, cancellation, retained task completion and descriptor restoration | Required |

## Acceptance commands

- Affected lifecycle, wizard and process-runner pytest files with pinned Python.
- `make vpnd-test vpnd-lint vpnd-parity-check` without baseline filters or skips.
- Package build/validation and an installed CLI prompt check using only synthetic inputs.
- `build-gate -- make check`, strict OpenSpec/task validation and independent review.
- Protected PR checks and exact-main CI after integration; the final step remains open until observed.

## Reproduction

On source `756f5a64cdea531b017fc78d0a01b57236aa27cb`, the complete local
check passed 10283 unit tests, 45 subtests and 70 shell tests, then failed one
of 387 vpnd tests at the reconverge review after SIGTERM. A single ordinary
rerun passed and was not treated as a fix.

A controlled actual-launcher PTY reproduction delivered SIGTERM to a retained
worker. Without terminal input the process stayed alive and synthetic plaintext
remained after three seconds, with no cleanup call. Sending a terminal refusal
then caused exit 143, one cleanup and plaintext removal. This is defect evidence,
not completed acceptance or proof of the failed run's exact kernel recipient.
