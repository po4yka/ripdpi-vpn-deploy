---
task_id: SEC-1791223987683372
change: sec-1791223987683372-bootstrap-restricted-management-on-existing-fleet-nodes
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
  then passed all 109 tests. Exact-source input freezing and rollout gates
  remain required before restoring the step's completed state.

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
| REQ-SEC-1791223987683372-001 | SEC-1791224948871987 | Named permanent/disposable classification and binding regression | required |
| REQ-SEC-1791223987683372-006 | SEC-1791224948871987 | Updated producer/inventory/guest build-marker binding | required |
| REQ-SEC-1791223987683372-002 | SEC-1791224949334227 | Real Linux startup permissions and lease expiry/identity tests | required |
| REQ-SEC-1791223987683372-003 | SEC-1791224949790667 | Managed-policy conversion, preserved listeners and refusal tests | required |
| REQ-SEC-1791223987683372-004 | SEC-1791224950240563 | Native interruption/reboot/original-policy rollback plus real SSH/SFTP | required |
| REQ-SEC-1791223987683372-005 | SEC-1791224950691731 | Exact protected CI, guarded staging, existing-node positive proof and cleanup | required |
