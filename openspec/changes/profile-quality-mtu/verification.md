---
task_id: OPS-1792759217301702
change: profile-quality-mtu
commit_sha: b2e9e935000dfb6c57287ef304833dbf99dfa4d9
local: blocked
local_evidence: On the merged dependency base, all 252 affected tests, Ruff, mypy, 387 vpnd tests, parity for 206 functions, 10 documentation tests, task checks and federation passed. The earlier full make check failed with 3 failures, 10192 passes and 45 passing subtests. The process cleanup failure also occurs on the clean baseline; CIC-1792759317705110 records that open gap. No assertion or guard was weakened.
remote_ci: required
remote_ci_evidence: Recipient PR 657 passed CI run 39982466513 and merged as 261f301910fafe5b40c724b35f65a87e669f3876 with the same tested tree. Its exact-main CI and producer PR 378 and main CI remain required.
dry_run: not_applicable
dry_run_evidence: This source change does not alter a deploy controller or rendered host deployment input; emitted recipient contracts are checked locally.
staging: not_applicable
staging_evidence: Owned local and hosted native client acceptance supplies the required positive runtime proof; no staging fleet is changed.
live: not_applicable
live_evidence: The opt-in source capability is delivered without enabling a deployed policy or changing a real host.
client: passed
client_evidence: Recipient runtime-state 301, data 974, service 2277, app 3002 and diagnostics 1655 tests passed, with full static analysis. All 73 native HTTP and QUIC packet-size tests and the Go fixture suite passed. An owned API 35 emulator passed all three new native scenarios with cleanup. Hosted API 27, 33, 35, 36 and 37 passed both quality scenarios; API 35 also passed authenticated REALITY quality measurement. Required native tests had no skips. English and Arabic large-text renders passed inspection. No physical-device result is claimed.
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
| REQ-QUALITY-ACCEPTANCE | OPS-1792759879627556 | Independent source review and recipient PR CI pass; full local gate has the known baseline gap; producer and exact-main CI remain required | blocked |

## Local gate gap

The full run failed in the SIGINT monitor cancellation check and two runtime
build checks. An immediate run of those three cases passed. The complete
baseline comparison passed 119 tests. A separate clean-baseline run recorded
in `docs/tasks/work/CIC-1792759317705110.md` reproduces the process-group
cleanup failure before this feature and the dependency update. These results
do not establish a fixed local gate. The last execution step remains open.

Hosted code and security reviews could not run because the account usage
limit was reached. Independent source reviews completed. Required security
CI checks passed for the recipient PR.

## Completion boundary

The paired recipient task is `po4yka/RIPDPI#TRN-1792759596946903`.
The source feature can close only after its positive runtime behavior and all
required evidence pass. Refusal paths or mocks alone are insufficient. Owned
native test environments do not establish a real fleet rollout or physical
device acceptance. No such external operation is requested by this change.
