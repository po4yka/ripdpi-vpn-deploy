---
task_id: SEC-1792842686096891
change: vpnd-review-signal-cleanup
commit_sha: "f6f6a8e77c3d8deaa2ddf37582e17f94c78fccbc"
local: "passed"
local_evidence: "The complete build-gate make check passed with exit 0 on unchanged 1eb91fb5d4544c32cb2760c6a1eb4f217add894c, whose tree equals main f6f6a8e77c3d8deaa2ddf37582e17f94c78fccbc. It passed 10283 core tests and 45 subtests, 70 Bats cases, 457 vpnd cases, parity for 206 functions, Ruff/Mypy and package reproducibility, offline installation and rollback. The portable selection excluded 253 Linux native cases; all seven hosted native lanes and cleanup passed in PR CI 40101164785 attempt 2."
remote_ci: "passed"
remote_ci_evidence: "Producer PR 382 passed CI 40101164785 attempt 2 and merged as f6f6a8e77c3d8deaa2ddf37582e17f94c78fccbc with the tested tree unchanged. Exact-main CI 40111525809 passed all 93 jobs, including required checks and all seven native lanes. The native job log confirms completed tests and owned staging removal; its step metadata remained stale after job success. CodeQL 40111525730, scorecard 40111525774, release-please 40111525771 and REALITY validation 40111525732 also passed on that main commit."
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
| REQ-DRF-REVIEW | SEC-1792842915023775 | Actual launcher PTY, worker-targeted signals, terminal authority and signal/answer ordering | passed |
| REQ-PYSAFE-CLEANUP | SEC-1792842915762104 | Cleanup once, plaintext removal, cancellation, retained worker completion and unchanged inherited descriptor flags | passed |

## Acceptance commands

- Affected lifecycle, wizard and process-runner pytest files with pinned Python.
- `make vpnd-test vpnd-lint vpnd-parity-check` without baseline filters or skips.
- Package build/validation and an installed CLI prompt check using only synthetic inputs.
- `build-gate -- make check`, strict OpenSpec/task validation and independent review.
- Protected PR checks and exact-main CI after integration must pass before task closure.

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
  input, ignored signals, EOF and signal priority. Queued-answer checks
  passed in the complete 457-test suite.
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
  finding. It is not acceptance evidence; the later complete final-tree run passed as recorded below.

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

## Completed local and PR acceptance

The complete local CLI gate passed with 10219 core tests and 45 subtests,
70 Bats cases, all 457 vpnd cases and parity for 206 functions. The final
combined producer gate then passed 10283 core tests and the same complete
CLI, package and parity checks on unchanged
`1eb91fb5d4544c32cb2760c6a1eb4f217add894c`. Its tree equals combined main
`f6f6a8e77c3d8deaa2ddf37582e17f94c78fccbc`.

PR 385 passed CI `40095997310` on
`9a3ef8768a0d80278bf629fb5c05b6a9dd405272`: all four platform test and
package lanes passed. All ten review threads are resolved. The PR merged
as `2610fd19e2709ab78365c015456d550a8406f718` with the same tree.
Its main CI `40100572409` failed contract-sync and the dependent aggregate
because the client already contained the hopping fixture supplied by PR
382. This intermediate result is not a passed gate. The combined main
contains that fixture; its complete CI passed as recorded below.

A Linux launcher regression initially timed out on SIGQUIT. The test
bootstrap now disables and checks core export after Python exec, then
runs the actual launcher. No production code, signal deadline, exit-code
assertion or terminal-descriptor assertion was changed for that test
isolation. Linux and macOS CI passed all 457 CLI cases and 206 parity
functions. The earlier crash-collector explanation remains unproved.

The installed native package passed all 12 actual CLI cases across both
commands: four worker-directed signals, approval and refusal. Every case
removed synthetic plaintext once; only approval reached mutation. No real
provider, SSH target or credential was used.

## Producer PR and combined main

Producer CI `40101164785` attempt 2 passed all 93 jobs on the exact tested
head. All seven native lanes and their cleanup passed. The full PR
snapshot contained 99 successful checks, one neutral Trivy comparison
warning and no pending or failed checks. No review or thread remained.
Attempt 1 lost contact with its hosted native runner; its last test result
and cleanup remain unconfirmed, and its underlying cause is unknown.
The bounded retry passed the actual suite and cleanup.

PR 382 merged as `f6f6a8e77c3d8deaa2ddf37582e17f94c78fccbc`. A direct
Git comparison found no tree difference from the tested producer head.
Exact combined-main CI `40111525809` passed all 93 jobs, including required
checks and all seven native lanes. CodeQL `40111525730`, scorecard
`40111525774`, release-please `40111525771` and REALITY validation
`40111525732` also passed on the same main commit.

The native job `120924105495` completed successfully at 17:20:26 UTC.
Its API step list still showed execution in progress and cleanup pending.
The terminal job log records the completed test groups, including 172
passing cases in the final group, followed by guarded removal of the
owned staging directory and successful job completion. This log, not the
stale step list, supplies the cleanup evidence.
