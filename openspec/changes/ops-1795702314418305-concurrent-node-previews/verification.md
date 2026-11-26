---
task_id: OPS-1795702314418305
change: ops-1795702314418305-concurrent-node-previews
commit_sha: null
local: passed
local_evidence: "On base a18e372a: make -k -j 4 check passed except task-check, which reported a stale board after the task start; the board was regenerated and make task-check passed. After the review fixes, tests/unit/test_deploy_controller.py (10 operation-lock cases), test_check_certs_callers.py, test_docs_index.py, test_docs_reference.py and test_agent_instructions.py passed (221 of 222 under -n auto; the generated-wrapper syntax-check test passed alone, a load-timing case)."
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: The change adds operator-machine locks and a runbook recipe; no remote state differs between staging and production.
live: not_applicable
live_evidence: A preview or a deploy sends the same commands to the node as before.
client: not_applicable
client_evidence: No client transport or payload changes.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-CNP-LOCK | OPS-1795702489297777 | `tests/unit/test_deploy_controller.py::test_operation_locks_keep_one_run_per_node_and_deploys_serial` (held node lock refuses `dry-run` and `deploy` with no host call; the next run takes the lock) and `::test_unsafe_operation_lock_refuses_before_any_host_call` (shared directory, symlinked and hard-linked lock) | Passed |
| REQ-CNP-SERIAL | OPS-1795702489297777 | Same parametrized test: a held fleet lock refuses a deploy of another node; a preview runs beside a held fleet lock and beside another node's lock | Passed |
| REQ-CNP-ISOLATION | OPS-1795702516853613 | `tests/unit/test_docs_index.py`, `test_docs_reference.py` on the recipe, which passes the secrets and inventory paths on the `make` command line | Passed |
| REQ-CNP-ISOLATION | OPS-1795702550913675 | Timed concurrent previews of two production aliases from one worktree | Pending |
