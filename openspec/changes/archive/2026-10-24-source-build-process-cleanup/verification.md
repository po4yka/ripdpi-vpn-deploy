---
task_id: ANS-1792773060904443
change: source-build-process-cleanup
commit_sha: ec655f037b5a1b7a26d8ddf4c673ef4e55791701
local: passed
local_evidence: "Full make check passed at dd9fef311cde792af2a2d94ff0ee5c7f7427e6e9 with exit 0. The integrated source commit has the identical tree. Portable tests: 10219 passed and 45 subtests passed; Bats: 70 passed; vpnd: 387 passed; parity: 206 functions; documentation: 10 passed."
remote_ci: passed
remote_ci_evidence: "PR 380 at dd9fef311cde792af2a2d94ff0ee5c7f7427e6e9 passed run 40069354263: 79 successful checks, 9 outside the selected scope and one neutral check. All required checks passed; all 12 review threads are resolved."
dry_run: not_applicable
dry_run_evidence: Source helper and portable test fix; no deployment is in scope.
staging: not_applicable
staging_evidence: No staging host or provider operation is in scope.
live: not_applicable
live_evidence: No live deployment is in scope.
client: not_applicable
client_evidence: The change does not alter a VPN client or transport contract.
artifact: not_applicable
artifact_evidence: No release package or protocol artifact is produced.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-BUILD-SESSION-OWNERSHIP | ANS-1792773632226275 | All 108 runtime-build cases passed in the local full gate and complete Linux shard union; real process probes and loss/release regressions retain exact group ownership | passed |
| REQ-BUILD-CLEANUP-FAILURE | ANS-1792773632226275 | Real cancellation, timeout, descendant, failed-cleanup and primary-cause regressions passed; review retained all five fatal cleanup handlers | passed |
| REQ-LOCAL-ASYNC-TESTS | ANS-1792773633446824 | Complete monitor 32, smoke 61 and site transaction 55 cases passed; the local smoke profile reduced transport operations from 65 to 16 without changing the 45-second deadline | passed |
| REQ-LOCAL-ASYNC-TESTS | ANS-1792773634640147 | Full local make check exited 0 at the tested head; hosted run 40069354263 completed successfully on that same head | passed |

## Initial observation

At base `8e0c4c16`, the complete runtime-build file reports one failure and 90 passed in 19.17 seconds. A separate real process probe confirms EPERM for an owned zombie-only group and ESRCH after its child is reaped. A live-descendant control is detected and reclaimed. This is diagnosis, not completed acceptance evidence.

## Final source verification

PR #380 merged as `ec655f037b5a1b7a26d8ddf4c673ef4e55791701`. Its tree and the tested head `dd9fef311cde792af2a2d94ff0ee5c7f7427e6e9` both equal `23f3bbb96beda1c34004b7c8b4a5853553c27666`. The commands ran at the tested head; the merge changes commit metadata only.

- Complete local `make check`: exit 0 in 7185.92 seconds, with the repository hash lock and pinned validation binaries. The portable suite passed 10219 tests and 45 subtests, deselected the canonical 253 native cases and reported 25 test warnings. All 70 Bats cases, 387 vpnd cases, parity for 206 functions and 10 documentation tests passed. Terraform, schema, lint, render, snapshot and parser gates passed too.
- Hosted run 40069354263: all 89 checks reached a terminal state with no failures. All 38 Molecule checks and the native acceptance/integration checks passed. The four portable reports have one identical collection and a disjoint completed union of 10219 cases, including all 256 cases in the four affected files.
- Independent source and security review approved the final diff. CodeQL has no warnings from this change; its five intentional fatal-cleanup notes were reviewed and explained. No analysis suppression or gate bypass was added.
- The shared role has no separate Molecule scenario. Hosted consumer Molecule and native integration checks provide its Linux runtime evidence.

## Earlier incomplete attempts

An old-base full run was stopped after main advanced. Its signal-interrupted results are not acceptance evidence. A later full run stopped at the unchanged cloud-init container deadline before pytest; instrumented and unchanged schema target runs then passed without changing the timeout or TLS checks. Before fixture pipelining, a complete smoke run had 60 passes and one 45-second Snell timeout. Three diagnostic single cases did not reproduce that timeout. The subsequent transport profile, complete 61-case smoke run and final full gate supply the current source evidence; the failed attempts remain failed.
