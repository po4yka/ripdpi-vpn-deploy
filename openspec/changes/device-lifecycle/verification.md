---
task_id: OPS-1792679812321846
change: device-lifecycle
commit_sha: 69bbf62f930de88a04106d43161dbc0dca511930
local: passed
local_evidence: Full make check completed with exit 0 on b0ae6b495f9372dbbe429d487967f383e6693c21; 10152 Python tests and 45 subtests, 387 vpnd tests and 10 documentation tests passed. Its tree e2ae4adcb2afa7daf38096f48105615f41e111c9 is identical to the recorded main commit. 253 Linux native cases were deselected on macOS and are covered separately by hosted Linux acceptance.
remote_ci: passed
remote_ci_evidence: Exact-head PR run 39923816763 passed all required checks, including all seven native jobs; 99 checks succeeded and one scan result was neutral. Main run 39934072990 for 69bbf62f930de88a04106d43161dbc0dca511930 passed all required checks and all seven native jobs with confirmed cleanup; 98 checks succeeded and the release dispatch was correctly skipped.
dry_run: required
dry_run_evidence: Manifest, literal dispatch, check-mode projection and typed revocation tests passed; an actual canonical deployment dry-run on the reviewed fleet remains unobserved.
staging: not_applicable
staging_evidence: No additional distinct staging rehearsal is required; the live category owns the outstanding positive external acceptance.
live: required
live_evidence: Real fleet issuance, all-grant refresh and complete runtime revocation remain unobserved; isolated native hosts and local publishers do not establish those operations.
client: required
client_evidence: Real isolated Linux positive, survivor and revoked credential paths passed. Actual issued-device acceptance on the target fleet and physical-device acceptance remain unobserved.
artifact: passed
artifact_evidence: Real SOPS issuance, all-grant refresh, private native output, output collision and lost publication acknowledgements passed.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DEVICE-OPERATION-PLAN | OPS-1792680221456320 | Complete declared inventory, retained publishers, source/input fences and real encrypted authority tests passed | passed |
| REQ-DEVICE-OPERATION-ISSUE | OPS-1792680221456320 | Usable encrypted issuance, private AWG/Naive artifacts and isolated Linux native positives passed; real fleet issuance and device acceptance remain unobserved | partial |
| REQ-DEVICE-OPERATION-REFRESH | OPS-1792680223324164 | Actual publisher CAS and TLS grants preserve URLs/expiry; lost acknowledgement and private output tests passed | passed |
| REQ-DEVICE-OPERATION-REVOKE | OPS-1792680222031123 | Portable recovery, real TLS 200-to-410, isolated Linux native denial and survivor access passed; complete live-fleet revocation remains unobserved | partial |
| REQ-DEVICE-OPERATION-RESUME | OPS-1792680222634877 | Real SOPS/publisher lost acknowledgements, immutable revocation intent and SIGKILL barrier tests passed | passed |

Step OPS-1792680223917464 owns complete local gates, independent review and
protected PR/exact-main CI. No unfinished or refusal-only path closes the task.


Independent review found and corrected grant-only revocation admission, P0-only
retained profile rendering and exact canary ownership for a real device sharing
its internal client name. Root fixes received follow-up read-only review.
The complete Linux integration suite passed real REALITY, Hysteria2 and Naive
lifecycle paths, including interrupted revocation and native cleanup. Source
implementation and isolated native acceptance do not claim physical-device or
production-fleet acceptance; the task remains in review with external categories
required.

## Integrated source evidence

[PR 369](https://github.com/po4yka/ripdpi-vpn-deploy/pull/369) integrated the
features. [PR 370](https://github.com/po4yka/ripdpi-vpn-deploy/pull/370),
[PR 372](https://github.com/po4yka/ripdpi-vpn-deploy/pull/372) and
[PR 374](https://github.com/po4yka/ripdpi-vpn-deploy/pull/374) corrected native
readiness, Snell listener allocation, recovery scheduling and AWG control
readiness. The source main commit is
`69bbf62f930de88a04106d43161dbc0dca511930`.
Runtime admission and denial assertions remain strict; recovery retains all
21 cases in three disjoint groups and the original 2400-second deadline.
Earlier failed or cancelled runs do not count as acceptance evidence.

The full `build-gate -- mise exec -- make check` passed on
`b0ae6b495f9372dbbe429d487967f383e6693c21`: 10,152 Python tests and 45 subtests,
387 vpnd tests and 10 documentation tests. Its Git tree
`e2ae4adcb2afa7daf38096f48105615f41e111c9` is identical to the source main commit
and hosted PR merge. No separate local run on the literal merge SHA is claimed.
The macOS run deselected 253 Linux native cases; it is not Linux runtime evidence.

[Exact-head PR CI](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39923816763)
passed all required checks: 99 successful checks and one neutral scan result,
including the required aggregate and all seven native jobs. Core passed
33 cases; recovery passed all 21 unique cases in disjoint groups of 6, 8 and 7,
with internal cleanup confirmed and no residual differences. Both runtime
partitions passed 9 cases. Integration passed 184 cases, including restored AWG
access, all Snell combinations and interrupted lifecycle scenarios, followed by
10 endpoint, 4 delivery and 169 topology cases. All owned environment cleanup
steps passed. Runtime and recovery overlap is not additional unique coverage.

Independent source review found no remaining actionable defect. AWG readiness
has 29 new portable regressions. Actual pinned Linux ARM64 binaries reproduced
the old worker's premature configuration with a diagnostic startup delay; the
corrected worker passed real HTTPS traffic, fresh handshakes and cleanup with
both that delay and the unchanged daemon, making one configuration write.
The failed earlier main run retained no setup stderr, so its precise failing
command is unknown; the reproduced startup defect is independently confirmed.

[Exact-main CI](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/39934072990)
passed on the recorded source commit: 98 successful checks and one expected
release-dispatch skip, including the required aggregate, all seven native jobs
and owned cleanup. The restored AWG access regression, 184 integration cases,
10 endpoint cases, 4 delivery cases and 169 topology cases passed. Core, recovery
and both runtime partitions passed the same complete case sets described above.
These isolated checks do not establish a real fleet rollout or physical-device
acceptance.
