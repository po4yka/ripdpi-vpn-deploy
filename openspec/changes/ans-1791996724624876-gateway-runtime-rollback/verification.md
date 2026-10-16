---
task_id: ANS-1791996724624876
change: ans-1791996724624876-gateway-runtime-rollback
commit_sha: e3c116843719049695ae740d2c82c998d0d1b2ca
local: passed
local_evidence: "Runtime source e3c116843719049695ae740d2c82c998d0d1b2ca with task-metadata edits: build-gate / mise make check exited 0. Portable pytest: 7507 passed, 166 native tests deselected, 43 subtests passed; vpnd: 320 passed and complete transfer of 206 baseline functions. Terraform tests/policies, production ansible-lint (740 files), 163 golden templates, parser compatibility, packaging and task contracts passed. Session-only PATH selected installed SOPS 3.13.3, age 1.3.1 and checksum-verified sing-box 1.14.3. The 286 focused regressions and disposable native quiescence/retirement probe also passed."
remote_ci: passed
remote_ci_evidence: "Run 38909820069 at source e3c116843719049695ae740d2c82c998d0d1b2ca: both native partitions passed, including first-adoption interruption recovery, runtime rollback, exact executable identity, refusal/SIGKILL compensation and a following ordinary converge. Xray, Hysteria and transport-egress Molecule scenarios and both complete site scenarios passed. The CI run passed: 69 successful jobs, 9 correctly unselected/skipped jobs, zero failures or cancellations, including the required summary. Companion PR checks also passed (73 success, 9 skipped, one neutral advisory)."
dry_run: not_applicable
dry_run_evidence: No real inventory or SSH transaction is planned.
staging: not_applicable
staging_evidence: Source and native validation does not establish a staging rollout.
live: not_applicable
live_evidence: No production deployment is planned.
client: passed
client_evidence: "Source e3c116843719049695ae740d2c82c998d0d1b2ca, CI 38909820069: the native Xray lifecycle case passed with real pinned authenticated client forwarding after rollback and complete refusal/SIGKILL recovery, plus a following ordinary converge. Native partition 2/2 passed its real Hysteria/ECH client cases. This is isolated Linux client evidence, not live fleet or registered vendor tunnel acceptance."
artifact: passed
artifact_evidence: "163 golden templates match. Portable tests validate direct-only and paired generation selection, immutable plans, per-gateway executable refusal, credential validation and the sole publication lane. At source e3c11684, both complete Molecule site scenarios and the Xray, Hysteria and transport-egress role scenarios passed in CI 38909820069."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-RTA-GATEWAY-ROLLBACK | ANS-1791996772545665 | Native rollback lane proving frontend and gateway executables, refusal compensation, and a following ordinary converge | passed: both native partitions, affected role/site scenarios, exact-source CI and complete gated local check |

## Acceptance scope

Source and isolated native acceptance are complete. Both native partitions passed
at source `e3c11684`, including rollback, complete compensation and the following
ordinary converge. The native lab exercises its selected direct gateway; portable
tests cover paired gateway selection and refusal of a wrong second executable.
Production deployment and registered vendor tunnel acceptance are outside this
source change's scope. Existing nodes converge once to adopt gateway receipt
claims before operator rollback; returning to the older publisher requires
complete-generation recovery or node recreation.
