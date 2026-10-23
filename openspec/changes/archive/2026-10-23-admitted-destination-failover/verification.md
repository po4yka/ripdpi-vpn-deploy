---
task_id: SEC-1792678909985498
change: admitted-destination-failover
commit_sha: 69bbf62f930de88a04106d43161dbc0dca511930
local: passed
local_evidence: Full make check completed with exit 0 on b0ae6b495f9372dbbe429d487967f383e6693c21; 10152 Python tests and 45 subtests, 387 vpnd tests and 10 documentation tests passed. Its tree e2ae4adcb2afa7daf38096f48105615f41e111c9 is identical to the recorded main commit. 253 Linux native cases were deselected on macOS and are covered separately by hosted Linux acceptance.
remote_ci: passed
remote_ci_evidence: Exact-head PR run 39923816763 passed all required checks, including all seven native jobs; 99 checks succeeded and one scan result was neutral. Main run 39934072990 for 69bbf62f930de88a04106d43161dbc0dca511930 passed all required checks and all seven native jobs with confirmed cleanup; 98 checks succeeded and the release dispatch was correctly skipped.
dry_run: not_applicable
dry_run_evidence: No inventory, Ansible task, configuration schema or deployment invocation changes; this scope is the installed Python helper implementation.
staging: not_applicable
staging_evidence: No staging deployment is requested or claimed; a later runtime rollout uses the existing guarded deployment workflow.
live: not_applicable
live_evidence: The changed installed helper is verified through real local destination sockets; provider mutation and deployed runtime rollout are outside this source-only capability.
client: not_applicable
client_evidence: No Android client code changes; owned local SOCKS clients exercise server helper behavior under local evidence.
artifact: not_applicable
artifact_evidence: Python source is installed by the existing role; this change does not produce a separately published binary artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-RDB-FAILOVER | SEC-1792679160742251 | `test_transport_destination_boundary.py` and `test_candidate_order_deduplicates_and_keeps_both_families_before_cap` | passed |
| REQ-PROTO-RDB-FAILOVER | SEC-1792679161411775 | `test_transport_destination_failover.py` real sockets: IPv4/IPv6 positive cases, third-candidate success, exact eight-attempt and two-open-socket caps, shared deadline and post-deadline closure | passed |
| REQ-PROTO-RDB-COMMIT | SEC-1792679162099578 | Both complete files cover exact winner-only pipelined bytes, no retry after reset, abrupt controls, cancellation/stop cleanup, restored capacity and existing UDP behavior | passed |

## Required commands

- `mise exec -- python3 -m pytest tests/unit/test_transport_destination_boundary.py tests/unit/test_transport_destination_failover.py --fail-on-skip`.
- `./taskctl openspec cli validate admitted-destination-failover --strict`.
- `make task-check` and `build-gate -- mise exec -- make check`.
- Required hosted PR checks on the exact reviewed implementation revision.

The local gateway is an owned SOCKS fixture that makes actual destination socket
connections. It is not a deployed Xray/Hysteria gateway. Positive source behavior,
complete local gates and successful PR and exact-main checks are observed. Refusals, fixture-only claims and omitted cases
do not qualify.

## Observed source review

The complete committed, staged, unstaged and untracked change was inspected.
No new listener, policy exception, DNS re-resolution, credential output, runtime
dependency or cross-layer mutation was introduced. All 88 destination-boundary
and failover tests passed with real destination socket traffic. Full local and
PR and exact-main gates passed. This review does not assert
deployment acceptance.

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
