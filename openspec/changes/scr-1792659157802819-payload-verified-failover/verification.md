---
task_id: SCR-1792659157802819
change: scr-1792659157802819-payload-verified-failover
commit_sha: 1dfe4bdadafe82e335735e7c78fbfcafe8a19521
local: required
local_evidence: The previous source passed complete make check with 9500 unit tests, 45 subtests and 379 vpnd tests. Two uncovered probe review defects are now corrected: deterministic combination of directional verdicts and HTTP/2 transport-error classification. Thirteen new regressions failed before the correction; the complete probe file now passes 70 tests including the retained real HTTP/TLS/SOCKS cases. Full make check for the corrected source is required before acceptance; prior success is not substituted for the new run.
remote_ci: required
remote_ci_evidence: Source 1dfe4bdadafe82e335735e7c78fbfcafe8a19521 passed all 92 jobs in CI 39805707332, including the native runtime and required aggregate, plus CodeQL, REALITY target validation, markdown links and instruction checks. The two review defects were not covered by that suite. Hosted acceptance for their corrected source remains required.
dry_run: not_applicable
dry_run_evidence: Source-only change; no real inventory or host access.
staging: not_applicable
staging_evidence: No deployment or real control origin is selected.
live: not_applicable
live_evidence: Live availability and recipient redistribution are outside this change.
client: required
client_evidence: RIPDPI source 6ec802d16d19a5c0f81f817be8cfc8f1205d29b5 passed full CI 39792086326 and was rebase-merged as identical-tree 33046c961cf4a501a1a8ac35243c6a171424fdc3. Additional valid-stale-AWG ownership correction is in PR 647, head b5b09af6ea93f5c076232e5d97529aa79ff93396: independent review, 9590 local JVM/runtime tests, 23 Detekt-rule tests and full static analysis passed. Complete hosted CI 39815952976 and merge are still required. The superseded lifecycle PR 646 is closed; its three separate lifecycle commits are included in 647.
artifact: passed
artifact_evidence: Canonical emitted payload fixture validates; 165 template snapshots and all four provider mock suites pass.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PAYLOAD-EXACT | SCR-1792659429313208 | Real local HTTP/TLS transfer and content-negative regressions; combined probe/inventory 88 passed | passed |
| REQ-PAYLOAD-PATH | SCR-1792659429313208 | Actual loopback SOCKS and ambient-proxy refusal tests | passed |
| REQ-FAILOVER-POLICY | SCR-1792659429925062 | Generated bundle, 134 recipient/schema tests and full coordinated client import/persistence suites on 5be355fd0397dfea71f7e68ec790a29c568be174 | passed |
| REQ-FAILOVER-SELECTION | SCR-1792659429925062 | Complete source 6ec802d16d19a5c0f81f817be8cfc8f1205d29b5 JVM, native and all five Android emulator suites passed; identical tree merged as 33046c961cf4a501a1a8ac35243c6a171424fdc3 | passed |
| REQ-ALT-OPT-IN | SCR-1792659430538417 | 80 listener checks, 165 render snapshots and all four provider mock suites | passed |
