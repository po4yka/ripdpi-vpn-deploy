---
task_id: SEC-1791223987683372
change: sec-1791223987683372-bootstrap-restricted-management-on-existing-fleet-nodes
commit_sha: 9d7113b52958c4b50c69158873bbe4cd482f3fa6
local: not_applicable
local_evidence: "Task dropped: Owner cancelled acceptance and requested removal of all acceptance resources"
remote_ci: not_applicable
remote_ci_evidence: "Task dropped: Owner cancelled acceptance and requested removal of all acceptance resources"
dry_run: not_applicable
dry_run_evidence: "Task dropped: Owner cancelled acceptance and requested removal of all acceptance resources"
staging: not_applicable
staging_evidence: "Task dropped: Owner cancelled acceptance and requested removal of all acceptance resources"
live: not_applicable
live_evidence: "Task dropped: Owner cancelled acceptance and requested removal of all acceptance resources"
client: not_applicable
client_evidence: "Task dropped: Owner cancelled acceptance and requested removal of all acceptance resources"
artifact: not_applicable
artifact_evidence: "Task dropped: Owner cancelled acceptance and requested removal of all acceptance resources"
---

# Verification

The observed earlier console recovery and SSH foundation belong to the parent
acceptance invocation. They motivate this change and do not verify its new
contract, policy conversion or enrollment. Implementation is in progress; the
feature and parent remain open.

## Observed local checks

- Acceptance correction on 2026-10-06: the workspace/caller step was reopened
  after actual renderer output refused bootstrap input validation. Ansible
  decoded the typed build label, but the custom parser retained its JSON quotes;
  the earlier handwritten fixture did not exercise that producer boundary.
  Enrollment did not run. The strengthened renderer-to-bootstrap regression
  failed before the decoder correction; the focused bootstrap/renderer suite
  then passed all 109 tests. Actual permanent-node inventory input freezing
  passed from the clean corrected source, including its source and host-key
  binding; the caller step was restored. Enrollment and rollout gates remain
  required and are not implied by that local preflight.

- Focused portable bootstrap, inventory, recovery and boundary checks passed.
  A combined run observed 353 passed before the final timer fixture changes;
  subsequent focused runs remain required for the final revision.
- Six Linux kernel tests passed: real namespace conversion, snapshot/apply/
  bridge-free restoration and exact inert-quartet addition/refusal. Service
  and node identity in those tests are explicit fixtures, not live evidence.
- The real PID1 expiry check passed in 90.14 seconds in private namespaces,
  including automatic kernel rule deletion, idempotent revoke and runtime
  directory modes. Identity and read-only root are explicit fixtures.
- `make check` in the operator worktree stopped on ignored historical staging
  tfvars formatting and its unavailable default Docker endpoint. Verify the
  same source in a clean checkout before treating this as a source regression.
- Task contracts and strict OpenSpec validation passed. Protected CI, actual
  read-only-root/identity, SSH/SFTP, staging, live and client gates remain required.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SEC-1791223987683372-001 | SEC-1791224948871987 | Dropped: Owner cancelled acceptance and requested removal of all acceptance resources | not_applicable |
| REQ-SEC-1791223987683372-006 | SEC-1791224948871987 | Dropped: Owner cancelled acceptance and requested removal of all acceptance resources | not_applicable |
| REQ-SEC-1791223987683372-002 | SEC-1791224949334227 | Dropped: Owner cancelled acceptance and requested removal of all acceptance resources | not_applicable |
| REQ-SEC-1791223987683372-003 | SEC-1791224949790667 | Dropped: Owner cancelled acceptance and requested removal of all acceptance resources | not_applicable |
| REQ-SEC-1791223987683372-004 | SEC-1791224950240563 | Dropped: Owner cancelled acceptance and requested removal of all acceptance resources | not_applicable |
| REQ-SEC-1791223987683372-005 | SEC-1791224950691731 | Dropped: Owner cancelled acceptance and requested removal of all acceptance resources | not_applicable |
