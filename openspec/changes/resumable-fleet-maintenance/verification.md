---
task_id: OPS-1793686022000048
change: resumable-fleet-maintenance
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: required
client_evidence: null
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-MAINT-RESUME | OPS-1793686512392634 | Required behavior and scoped acceptance checks | Pending |
| REQ-MAINT-RESUME-CONVERGED | OPS-1794070939441144 | Required behavior and scoped acceptance checks | Pending |
| REQ-MAINT-RELEASE | OPS-1793686512392634 | Required behavior and scoped acceptance checks | Pending |
| REQ-MAINT-KIT | OPS-1793686512392634 | Required behavior and scoped acceptance checks | Pending |
| REQ-MAINT-SERIAL | OPS-1793686512392634 | Required behavior and scoped acceptance checks | Pending |
| REQ-MAINT-RESTORE | OPS-1793686512392634 | Required behavior and scoped acceptance checks | Pending |
| REQ-MAINT-DRIFT | OPS-1793686512392634 | Required behavior and scoped acceptance checks | Pending |
| REQ-MAINT-IP | OPS-1793686512392634 | Required behavior and scoped acceptance checks | Pending |
| REQ-MAINT-CI | OPS-1793686512392634 | Required behavior and scoped acceptance checks | Pending |
| REQ-MAINT-CREDENTIALS | OPS-1793686512392634 | Required behavior and scoped acceptance checks | Pending |

| REQ-MAINT-CATALOG | OPS-1794657885705909 | `test_catalog_reconciles_only_accepted_core_and_resumes_publication` | Local passed |
| REQ-MAINT-GENERATE | OPS-1794657885705909 | `test_generate_selects_catalog_nodes_and_rejects_unsafe_dependencies` | Local passed |
| REQ-MAINT-SCHEDULE | OPS-1794657918337568 | Real child, real Ansible drift, backup readback and expiry, cron/launchd boundary tests in `test_operator_automation.py` | Local passed |

## Operator automation local evidence

`build-gate -- mise exec -- make -k -j 4 check PYTEST_WORKERS=4` ran all
checks. The unit suite passed 11,966 tests and 45 subtests. The vpnd suite
passed 551 tests. Terraform mock-provider suites passed 270 tests.

The full command returned exit 2 for two existing comment-length violations
and a stale provider-cache path in the native lifecycle fixture. Both were
corrected. `mise exec -- env ANSIBLE_CONFIG=ansible/ansible.cfg ansible-lint
ansible` then passed. The native lifecycle test file passed all 18 tests after
the fixture used the canonical validation provider cache. All other checks
in the `make -k` run passed. No full gate rerun was needed under the repository
rule for isolated failing-check fixes.

Independent security review passed after fixes to frozen backup inputs,
retained recovery references, strict drift counts, expiry, and scheduler paths.
These results prove local behavior. No real scheduler was installed, and no
live deployment, drift check, or offsite backup ran. Hosted CI and the parent
task's separate live acceptance requirements remain open.
