---
task_id: SCR-1792659157802819
change: scr-1792659157802819-payload-verified-failover
commit_sha: bf7f9baef8130246a255f503909457f676ab46dc
local: passed
local_evidence: On tested c77adec1ba63c675552ed71fa8bdebd250275153, task contracts passed with 65 tasks and 235 steps; ci-fast passed with 9542 unit tests, 45 subtests and 387 vpnd tests. The original make check exited 2 because its all-local-refs gitleaks scan found false positives in two unrelated commits outside HEAD and origin/main ancestry. Canonical make validate then passed in a full single-branch clone of the unchanged tested SHA, without scan suppressions or shallow history. The complete probe file passed 70 tests after 13 new regressions failed before correction. The accepted merge has the identical complete Git tree.
remote_ci: passed
remote_ci_evidence: CI 39822440351 attempt 2 completed successfully on c77adec1ba63c675552ed71fa8bdebd250275153. All nine protected checks passed; PR 357 had 97 successful checks and one optional neutral Trivy check. Native runtime, transport and recovery checks passed; the stalled Terraform job was rerun before the final required aggregate passed. All six review threads were resolved. Squash-merged source bf7f9baef8130246a255f503909457f676ab46dc has the identical complete tree.
dry_run: not_applicable
dry_run_evidence: Source-only change; no real inventory or host access.
staging: not_applicable
staging_evidence: No deployment or real control origin is selected.
live: not_applicable
live_evidence: Live availability and recipient redistribution are outside this change.
client: passed
client_evidence: RIPDPI PR 647 merged as ede4099f5e53023c03e4e6875cdb8521cb627d56, with the identical complete tree as tested b5b09af6ea93f5c076232e5d97529aa79ff93396. Full CI 39815952976 attempt 1 passed with 46 successful jobs and 18 routed skips, including Full/Simple instrumentation on API 27/33/35/36/37 and API 35 JNI strategy and real Xray-provider TUN acceptance. Independent review, 9590 local JVM tests and 23 Detekt-rule tests passed; the final local run reused 286 unchanged runtime-state tests up-to-date. This source includes the valid-stale-AWG ownership correction and the validated historical consumer closure. The separate PR 649 harness correction is not credited as accepted here.
artifact: passed
artifact_evidence: Canonical emitted payload fixture validates; 165 template snapshots and all four provider mock suites pass.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PAYLOAD-EXACT | SCR-1792659429313208 | All 70 probe regressions passed, including real local HTTP/TLS/SOCKS transfers, content-negative cases, deterministic directional combination and HTTP/2 transport-error classification | passed |
| REQ-PAYLOAD-PATH | SCR-1792659429313208 | Actual loopback SOCKS and ambient-proxy refusal tests | passed |
| REQ-FAILOVER-POLICY | SCR-1792659429925062 | Canonical generated bundle/schema and coordinated client import/persistence suites passed in the final producer and consumer gates | passed |
| REQ-FAILOVER-SELECTION | SCR-1792659429925062 | Complete consumer b5b09af6ea93f5c076232e5d97529aa79ff93396 JVM, native and five Android emulator suites passed; identical tree merged as ede4099f5e53023c03e4e6875cdb8521cb627d56, including accepted AWG ownership and recovery | passed |
| REQ-ALT-OPT-IN | SCR-1792659430538417 | 80 listener checks, 165 render snapshots and all four provider mock suites | passed |

## Accepted source and validation boundaries

Producer PR 357 was squash-merged as `bf7f9baef8130246a255f503909457f676ab46dc`.
That revision and tested `c77adec1ba63c675552ed71fa8bdebd250275153` both have complete
tree `7f9d6b989b6b6871a785923e7cc89f036d6e5385`. Consumer PR 647's tested and merged
revisions both have tree `72c9edb2b3c770ef5a2379e3bca7e0dead916aa7`.

The original aggregate `make check` did not exit successfully. Its task-contract
and `ci-fast` components passed, while `validate` failed on gitleaks findings in
unrelated local refs. The unchanged source subsequently passed canonical
`make validate` in a full, isolated single-branch clone: all four Terraform roots,
gitleaks over 1221 reachable commits, Ansible production lint with zero failures
or warnings in 759 files, and playbook syntax. No rules, allowlists or assertions
were weakened. The syntax check used no real inventory; expected implicit-localhost
warnings do not constitute live-host validation.

The earlier producer CI pass did not cover two probe defects. New regressions
failed 13 cases before the correction, and all 70 probe cases passed afterward.
HTTP/2 exit-code cases inject subprocess outcomes to test classification; real
HTTP/TLS/SOCKS cases remain separate positive and negative transport evidence.
CodeQL's adjacent-string warning was reviewed against the Python AST: the two
literals intentionally form one complete `python -c` program. No suppression or
security configuration change was needed.

The final hosted run retained successful native/runtime/transport/recovery
results and recovered the stalled Terraform job through a targeted rerun before
the required aggregate passed. The optional neutral Trivy check and unavailable
cloud review are not reported as successful scans. The independent consumer
test-harness correction in PR 649 remains outside this acceptance.

This closes source delivery only. It does not claim deployment, production or
filtered-network availability, physical-device acceptance, or credential use.
