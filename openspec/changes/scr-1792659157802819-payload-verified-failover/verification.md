---
task_id: SCR-1792659157802819
change: scr-1792659157802819-payload-verified-failover
commit_sha: 18a1ff2106bff8f1aedd3835c57595f9310dc358
local: passed
local_evidence: Complete make check passed on source 18a1ff2106bff8f1aedd3835c57595f9310dc358: 9500 unit tests, 45 subtests, 379 vpnd tests, all task, validation, Bats, Terraform and ci-fast gates. The 230 native-only cases were deselected by the established local suite and exercised separately in hosted native acceptance. Validation used checksum-verified sing-box 1.14.3 and pinned SOPS/age binaries with the CI test umask after local tool-version, HOME-shim and umask failures were diagnosed. No assertion or gate was weakened. Integration commit 4c78361d preserves all 49 feature-only runtime/contract/test files byte-identically; docs-check passed 10 tests, the combined documentation/listener suite passed 93 tests with one stale link corrected and the full seven-test agent-instructions suite then passed. All merge hooks and independent integration review passed.
remote_ci: required
remote_ci_evidence: Source 18a1ff2106bff8f1aedd3835c57595f9310dc358, CI run 39770409867. All four pytest groups, provider suites, Molecule, linters, vpnd and transport/recovery jobs passed. Native runtime job 119830304310 passed its complete warm-publication, rollback, ECH, 168-test native, 10-test delivery, four-test matrix, 169-test topology and final 10-test AWG suites. This was one targeted retry after job 119796296437 exhausted its time budget following a 15-minute Ubuntu package download; no code, assertion or timeout changed. Only post-client-merge contract synchronization remains required; the overall run is not yet accepted.
dry_run: not_applicable
dry_run_evidence: Source-only change; no real inventory or host access.
staging: not_applicable
staging_evidence: No deployment or real control origin is selected.
live: not_applicable
live_evidence: Live availability and recipient redistribution are outside this change.
client: passed
client_evidence: RIPDPI source 6ec802d16d19a5c0f81f817be8cfc8f1205d29b5 passed complete CI 39792086326, including Full and Simple JVM suites, coverage, static analysis, native tests, all five Android API 27/33/35/36/37 emulator suites, release builds and required aggregate; fleet fixtures, CodeQL, harness and secret scan also passed. PR 645 was rebase-merged as 33046c961cf4a501a1a8ac35243c6a171424fdc3 with identical full tree. Earlier cold-start instrumentation and two test-synchronization failures were fixed before this acceptance. Both client tasks remain traceable through the separate lifecycle follow-up PR 646.
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
