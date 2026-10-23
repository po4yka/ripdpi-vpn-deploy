---
task_id: OPS-1792673523985723
change: device-server-migration
commit_sha: 69bbf62f930de88a04106d43161dbc0dca511930
local: passed
local_evidence: Full make check completed with exit 0 on b0ae6b495f9372dbbe429d487967f383e6693c21; 10152 Python tests and 45 subtests, 387 vpnd tests and 10 documentation tests passed. Its tree e2ae4adcb2afa7daf38096f48105615f41e111c9 is identical to the recorded main commit. 253 Linux native cases were deselected on macOS and are covered separately by hosted Linux acceptance.
remote_ci: passed
remote_ci_evidence: Exact-head PR run 39923816763 passed all required checks, including all seven native jobs; 99 checks succeeded and one scan result was neutral. Main run 39934072990 for 69bbf62f930de88a04106d43161dbc0dca511930 passed all required checks and all seven native jobs with confirmed cleanup; 98 checks succeeded and the release dispatch was correctly skipped.
dry_run: required
dry_run_evidence: Blue-green lifecycle and operator-path suites passed preview refusal, retirement-gate and retained-inventory checks; an actual canonical deployment dry-run remains unobserved.
staging: not_applicable
staging_evidence: No additional distinct staging rehearsal is required; the live category owns the outstanding positive external acceptance.
live: required
live_evidence: A real server replacement, stable-origin publication and device-gated retirement remain unobserved; source integration does not satisfy these retained external requirements.
client: required
client_evidence: Client source and shared contract checks passed; the owned emulator proved real Hysteria2 payload and explicit receipt export. Real Reality, XHTTP and active AmneziaWG migration paths and physical-device acceptance remain unobserved.
artifact: not_applicable
artifact_evidence: Repository source and contract fixtures are the deliverables; no separate release artifact is requested.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DEVICE-MIGRATION-PLAN | OPS-1792674210176785 | test_device_migration.py, test_device_migration_io.py and test_device_migration_review.py passed, including strict inventory/pins and mutable-input fencing | passed |
| REQ-DEVICE-MIGRATION-CREDENTIALS | OPS-1792674210176785 | test_device_migration_credentials.py passed with real test-only SOPS/age roundtrips and complete journal schema validation | passed |
| REQ-DEVICE-MIGRATION-PUBLISH | OPS-1792674211571053 | test_subscription_migration.py and test_device_migration_route.py passed; actual local publisher CAS, loopback trusted TLS, timeout, lost acknowledgement and cleanup | passed |
| REQ-DEVICE-MIGRATION-RECEIPT | OPS-1792674215498584 | Shared vectors and paired client source passed; actual Hysteria2 emulator payload and explicit received/path-tested export passed server HMAC and exact-byte checks. Real Reality, XHTTP and active AWG migration acceptance remains unobserved | partial |
| REQ-DEVICE-MIGRATION-RETIREMENT | OPS-1792674212965582 | test_device_migration.py, test_blue_green_lifecycle.py, test_device_migration_inventory.py and test_audit_operator_paths.py passed; complete operator-path suite 26 passed, inventory suite 8 passed | passed |

## Completion boundary

Step OPS-1792674228402400 records independent review, complete local gates and
exact-SHA protected PR/main CI. Fixtures establish controller behavior and local
runtime operations; they do not establish deployed or physical-device acceptance.

## Current validation

The combined controller, IO, route and independent-review suites passed (48
tests); the expanded frozen-transport review suite passed with 40 tests. The
subscription template snapshot, example secrets schema and all 165 render
snapshots passed. Full local and protected PR gates passed on the integrated
source tree, including exact server main CI. The remaining real client-path
acceptance remains required. Source integration is not deployment or physical-device acceptance.

Client [PR 648](https://github.com/po4yka/RIPDPI/pull/648) merged as
`9137bec5f93d24547146e1a205e7d86c23fc23f0`; its
[main CI](https://github.com/po4yka/RIPDPI/actions/runs/39870281383) passed.
Client [PR 651](https://github.com/po4yka/RIPDPI/pull/651) preserves REVIEW with
the four-transport step open at `b045a630ae6f45b94ddc0c5b53e1c20532c8e532`;
its [main CI](https://github.com/po4yka/RIPDPI/actions/runs/39880248701) completed
with 47 successful jobs and 17 conditional skips. Neither hosted emulator matrix
proves the three outstanding real migration paths or physical-device acceptance.

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
