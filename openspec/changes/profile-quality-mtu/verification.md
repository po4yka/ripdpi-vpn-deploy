---
task_id: OPS-1792759217301702
change: profile-quality-mtu
commit_sha: "f6f6a8e77c3d8deaa2ddf37582e17f94c78fccbc"
local: "passed"
local_evidence: "The complete build-gate make check passed with exit 0 on unchanged 1eb91fb5d4544c32cb2760c6a1eb4f217add894c, whose tree equals main f6f6a8e77c3d8deaa2ddf37582e17f94c78fccbc. It passed 10283 core tests and 45 subtests, 70 Bats cases, 457 vpnd cases, parity for 206 functions, Ruff/Mypy and package reproducibility, offline installation and rollback. The portable selection excluded 253 Linux native cases; all seven hosted native lanes and cleanup passed in PR CI 40101164785 attempt 2."
remote_ci: "passed"
remote_ci_evidence: "Producer PR 382 passed CI 40101164785 attempt 2 and merged as f6f6a8e77c3d8deaa2ddf37582e17f94c78fccbc with the tested tree unchanged. Exact-main CI 40111525809 passed all 93 jobs, including required checks and all seven native lanes. The native job log confirms completed tests and owned staging removal; its step metadata remained stale after job success. CodeQL 40111525730, scorecard 40111525774, release-please 40111525771 and REALITY validation 40111525732 also passed on that main commit."
dry_run: not_applicable
dry_run_evidence: This source change does not alter a deploy controller or rendered host deployment input; emitted recipient contracts are checked locally.
staging: not_applicable
staging_evidence: Owned local and hosted native client acceptance supplies the required positive runtime proof; no staging fleet is changed.
live: not_applicable
live_evidence: The opt-in source capability is delivered without enabling a deployed policy or changing a real host.
client: passed
client_evidence: "The recipient quality and packet-size suites, actual native traffic, owned API 35 emulator checks and large-text English/Arabic renders passed. The catalogue migration defect was fixed in recipient PR 659; all four migration cases with the actual stored schema passed in the 1282-test data/runtime suite. Recipient main e22c8d66d8fa0c9245eb5bf8ef802e24028d0f48 passed CI 40085973754 on APIs 27, 33, 35, 36 and 37, including all required quality and permission checks; API 35 also passed authenticated REALITY quality measurement. Recipient closure main fbd57b32b0eb24a915ef3d96c57b0686d8444d97 passed all four main workflows. No physical-device result is claimed."
artifact: not_applicable
artifact_evidence: Source and contract fixtures are the deliverables; no application release or deployed artifact is requested.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-QUALITY-CONTRACT | OPS-1792759876681957 | All 252 affected producer tests passed on the merged base; paired parser, stored policy and pending journal migration tests passed | passed |
| REQ-FAILOVER-POLICY | OPS-1792759876681957 | Version 2 emission, absent quality and rejected invalid versions pass; paired contract files match byte for byte | passed |
| REQ-QUALITY-MEASUREMENT | OPS-1792759877415719 | Real HTTP/TLS/SOCKS and concurrent HEAD checks pass; native authenticated REALITY transfer and partial-load cleanup pass | passed |
| REQ-QUALITY-BUDGET | OPS-1792759878148038 | Durable reservation, restart, policy changes, failed writes and cancellation pass in the paired service and native suites | passed |
| REQ-QUALITY-SELECTION | OPS-1792759878148038 | Both hosted quality scenarios pass on all five API levels, including sustained comparison and applied-runtime confirmation | passed |
| REQ-QUALITY-DIAGNOSIS | OPS-1792759878904355 | Diagnostics 1655 tests and native HTTP/QUIC 73 tests pass; large-text English and Arabic views inspected; all 10 locale sets checked | passed |
| REQ-QUALITY-ACCEPTANCE | OPS-1792759879627556 | Independent source review, qualified recipient main, full local gate and producer PR CI passed; exact combined-main CI passed | passed |

## Earlier local gate gap

The full run failed in the SIGINT monitor cancellation check and two runtime
build checks. An immediate run of those three cases passed. The complete
baseline comparison passed 119 tests. A separate clean-baseline run recorded
in `docs/tasks/work/CIC-1792759317705110.md` reproduces the process-group
cleanup failure before this feature and the dependency update. Those results
did not establish a fixed local gate. Later acceptance is recorded below;
the complete current gate passed as recorded below.

Hosted code and security reviews could not run because the account usage
limit was reached. Independent source reviews completed. Required security
CI checks passed for the recipient PR.

## Completion boundary

The paired recipient task is `po4yka/RIPDPI#TRN-1792759596946903`.
The source feature can close only after its positive runtime behavior and all
required evidence pass. Refusal paths or mocks alone are insufficient. Owned
native test environments do not establish a real fleet rollout or physical
device acceptance. No such external operation is requested by this change.

## Current source acceptance

The earlier feature checks passed runtime-state 301, data 974, service 2277,
app 3002 and diagnostics 1655 tests, with full static analysis. All 73 native
HTTP and QUIC packet-size tests and the Go fixture suite passed. The owned
API 35 emulator passed all three new native scenarios with cleanup.

The earlier process-group cleanup gap was resolved separately by PR 380 at
`ec655f037b5a1b7a26d8ddf4c673ef4e55791701`. Its committed task record
`CIC-1792759317705110` contains the complete local and hosted acceptance.
This change does not alter that completed task or claim its work.

Producer PR 378 merged as `2e6a8ff21b468e225ba5eca72505b52f513a3692`;
its exact-main CI `40002002857` passed. The current producer tree also
contains the separate terminal-review fix from PR 385 and the hopping
contract from PR 382. Its complete local gate passed on unchanged
`1eb91fb5d4544c32cb2760c6a1eb4f217add894c`, with the same tree at
`f6f6a8e77c3d8deaa2ddf37582e17f94c78fccbc`.

The catalogue audit found that typed decode ran before stored-policy
migration. Recipient PR 659 fixes that schema boundary. All four tests use
actual stored catalogue schemas; the data/runtime suite passed 1282 tests
with no failures or skips. The final recipient main and its task closure
passed as recorded in the client evidence above.

An earlier API 36 permission test timed out on recipient main. Its cause
was not established, and no permission assertion or timeout was weakened.
The later qualified main passed all required permission and quality cases
on all five API levels. This record does not claim a product fix for the
earlier timeout.

Packet-size diagnosis reports a measured direct-path lower bound. It does
not claim an exact tunnel MTU. Owned test peers and emulators do not prove
a deployed fleet rollout or physical-device acceptance.

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
