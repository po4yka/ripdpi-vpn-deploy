---
task_id: ANS-1786277767052693
change: ans-1786277767052693-add-network-exposure-denylist-gate
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: "Pre-merge implementation candidate 5581b6fa31efa01fc11d3c136ba32f558bf8f4af passed CI run 33080350367, all 53 jobs including both full-stack variants, baseline on both distributions, AWG, exposure and firewall. The specification still requires final merge-SHA evidence after the external acceptance blockers are satisfied."
dry_run: blocked
dry_run_evidence: "Native Linux Molecule passed in run 33080350367. The operator-reviewed signed artifact, non-mutating real-inventory review and staging promotion/rollback evidence remain pending; no approved staging target is available."
staging: blocked
staging_evidence: "Native Linux Molecule passed in run 33080350367. The operator-reviewed signed artifact, non-mutating real-inventory review and staging promotion/rollback evidence remain pending; no approved staging target is available."
live: not_applicable
live_evidence: Live enforcement requires a later owner-authorized change.
client: blocked
client_evidence: "Both new exposure JSON schemas must be mirrored to the RIPDPI vendored contract before the full implementation can pass contract-sync. No client runtime behavior is changed."
artifact: blocked
artifact_evidence: "Native Linux Molecule passed in run 33080350367. The operator-reviewed signed artifact, non-mutating real-inventory review and staging promotion/rollback evidence remain pending; no approved staging target is available."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-ANS-1786277767052693-001 | TST-1786277767052610 | Pending | required |
| REQ-ANS-1786277767052693-002 | ANS-1786277767052243 | Pending | required |
| REQ-ANS-1786277767052693-003 | ANS-1786277767052018 | Pending | required |
| REQ-ANS-1786277767052693-004 | ANS-1786277767052707 | Pending | required |
| REQ-ANS-1786277767052693-005 | DOC-1786277767052241 | Pending | required |

## Observed implementation checks (2026-08-27)

`make check` exited 0: 1107 unit tests passed with one skipped test,
55 Bats checks, 83 Terraform mock tests, 45 Conftest tests, 102 snapshots,
strict Ansible lint, Rust MSRV and dependency checks, and 172 release tests.
The subsequent QR legacy-output regression slice passed 28 tests; full-stack
fixture guards passed for both inventories and the 14-test verification slice
passed with inherited privilege escalation enabled. Native Linux Molecule subsequently passed in run 33080350367 on exact
5581b6fa31efa01fc11d3c136ba32f558bf8f4af (all 53 jobs). Real staging/live
acceptance and final merge-SHA verification remain separate requirements.
