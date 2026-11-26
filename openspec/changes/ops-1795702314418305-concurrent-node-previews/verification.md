---
task_id: OPS-1795702314418305
change: ops-1795702314418305-concurrent-node-previews
commit_sha: e16a6a59eea0264000056e4f57fa11d3f36c8142
local: passed
local_evidence: "On base a18e372a: make -k -j 4 check passed except task-check, which reported a stale board after the task start; the board was regenerated and make task-check passed. After the review fixes, tests/unit/test_deploy_controller.py (10 operation-lock cases), test_check_certs_callers.py, test_docs_index.py, test_docs_reference.py and test_agent_instructions.py passed (221 of 222 under -n auto; the generated-wrapper syntax-check test passed alone, a load-timing case)."
remote_ci: passed
remote_ci_evidence: "po4yka/ripdpi-vpn-deploy ci run 45856572048 on main at e16a6a59e (pull request 748, the lock implementation and runbook recipe): completed with success."
dry_run: passed
dry_run_evidence: "Concurrent check-mode previews of node-a and node-b from one clean worktree at source e16a6a59e, each with its own decrypted secrets path and an explicit inventory passed on the make command line, started together at 2026-11-26T19:51:39Z: node-a dry-run 1040.5 s (1265 tasks, ok=696 changed=2 unreachable=0 failed=0), node-b dry-run 1382.7 s (1305 tasks, ok=723 changed=2 unreachable=0 failed=0); both passed with plaintext absent, wall time 23 min 5 s against 40 min 23 s for the two previews one after the other. While both controllers held node-node-a.lock and node-node-b.lock, a third dry-run of node-a was refused with node-operation-in-progress (exit 2) before it read secrets or contacted the host."
staging: not_applicable
staging_evidence: The change adds operator-machine locks and a runbook recipe; no remote state differs between staging and production.
live: not_applicable
live_evidence: A preview or a deploy sends the same commands to the node as before.
client: not_applicable
client_evidence: No client transport or payload changes.
artifact: passed
artifact_evidence: "Operator-kit receipts preview-timing-20261126/conc-node-a.json and conc-node-b.json (source revision, clean checkout, per-goal exit codes, durations and SHA-256 of the age-encrypted logs) and conc-node-a-refusal.txt (exit code and refusal category)."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-CNP-LOCK | OPS-1795702489297777 | `tests/unit/test_deploy_controller.py::test_operation_locks_keep_one_run_per_node_and_deploys_serial` (held node lock refuses `dry-run` and `deploy` with no host call; the next run takes the lock) and `::test_unsafe_operation_lock_refuses_before_any_host_call` (shared directory, symlinked and hard-linked lock) | Passed |
| REQ-CNP-SERIAL | OPS-1795702489297777 | Same parametrized test: a held fleet lock refuses a deploy of another node; a preview runs beside a held fleet lock and beside another node's lock | Passed |
| REQ-CNP-ISOLATION | OPS-1795702516853613 | `tests/unit/test_docs_index.py`, `test_docs_reference.py` on the recipe, which passes the secrets and inventory paths on the `make` command line | Passed |
| REQ-CNP-ISOLATION | OPS-1795702550913675 | Concurrent previews of node-a (1040.5 s) and node-b (1382.7 s) from one worktree at e16a6a59e, both passed with no unreachable or failed host; wall time 23 min 5 s | Passed |
| REQ-CNP-LOCK | OPS-1795702550913675 | Live: a third dry-run of node-a during its preview refused with `node-operation-in-progress` before any host call | Passed |
