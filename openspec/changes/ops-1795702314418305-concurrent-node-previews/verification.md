---
task_id: OPS-1795702314418305
change: ops-1795702314418305-concurrent-node-previews
commit_sha: null
local: required
local_evidence: null
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
| REQ-CNP-LOCK | OPS-1795702489297777 | Controller tests for refusal of a held alias and release after failure | Pending |
| REQ-CNP-SERIAL | OPS-1795702489297777 | Controller tests for a second deploy and for a preview beside a deploy | Pending |
| REQ-CNP-ISOLATION | OPS-1795702516853613 | `make docs-check` on the concurrent preview recipe | Pending |
| REQ-CNP-ISOLATION | OPS-1795702550913675 | Timed concurrent previews of two production aliases from one worktree | Pending |
