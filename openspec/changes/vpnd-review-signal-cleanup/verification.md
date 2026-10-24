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
artifact: passed
artifact_evidence: The built native package was installed offline. All 12 real installed-CLI cases passed across both commands, covering four worker-directed signals, terminal approval and terminal refusal. Each cleaned synthetic plaintext once; only approval reached mutation.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DRF-REVIEW | SEC-1792842915023775 | Actual launcher PTY, worker-targeted signals, terminal authority and signal/answer ordering | Source checks passed; final gates pending |
| REQ-PYSAFE-CLEANUP | SEC-1792842915762104 | Cleanup once, plaintext removal, cancellation, retained worker completion and unchanged inherited descriptor flags | Source checks passed; final gates pending |

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

## Source regression evidence

- Worker-directed review signals: all eight original cases failed before the
  fix. The completed signal/review selection passed 55 tests, including partial
  input, ignored signals, queued answers, EOF and signal priority.
- Repeated worker cancellation: both retained-worker cases failed before the
  fix. The tests now prove that caller cleanup waits for worker completion and
  preserves the original cancellation or worker error.
- Initial confirmation: ten real-launcher cases failed before the private-FD
  fix. They cover both commands and all four handled signals plus SIGKILL. The
  final resource/authority/cancellation selection passed 39 tests and proves
  inherited flags stay unchanged during input and after abrupt termination.
- Ruff and Mypy passed for 39 source files. Independent source review found no
  remaining actionable defect after both cancellation and descriptor fixes.
- The first complete vpnd run passed 445 tests and failed one installed-package
  case because it built before the new module was staged. This is not a passed
  gate. The final staged-tree suite passed all 457 tests. Ruff and Mypy passed;
  the subsequent parity check passed all 206 baseline functions. The initial
  multi-goal Make command exited 2 because parallel Make ran parity before the
  suite finished. The separate parity command used the completed suite result
  and exited 0. The installed native package then passed all 12 signal, approval
  and refusal cases with the actual CLI and synthetic external infrastructure.
- An earlier full repository check was interrupted after the descriptor review
  finding. It is not acceptance evidence; the final tree requires a fresh run.

## Review disposition

Independent source review passed after the retained-worker and private-FD fixes.
Structured review with priority through P2 exited 1 with two findings that were
independently checked and rejected as regressions. The result is not a clean
structured-review exit:

- The old synchronous `readline` was also unbounded. Continuous locally supplied
  noncanonical input adds no new remote input path; no new normal-flow failure
  was identified. A line-size policy is separate optional hardening.
- A same-PTY comparison on Python 3.12.15 and Darwin did not reproduce a partial
  VEOF hang. After `n` plus VEOF, the new reader returned false immediately;
  the old reader required another VEOF. No change was made for this finding.
