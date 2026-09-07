---
task_id: CIC-1788741692326070
change: cic-1788741692326070-require-committed-review-before-terminal-close
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: repository-local task tooling does not render or consume deployment inputs
staging: not_applicable
staging_evidence: no deployable runtime or infrastructure behavior changes
live: not_applicable
live_evidence: no provider, host, service, or production behavior changes
client: not_applicable
client_evidence: no client emitter, profile, artifact, or traffic path changes
artifact: not_applicable
artifact_evidence: no release artifact is produced
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-CIC-1788741692326070-001 | CIC-1788741818664643 | Command-level committed-review refusal, success, path, identity, and no-write regressions | pending |
| REQ-CIC-1788741692326070-002 | CIC-1788747290039529 | Canonical archive skill ordering and matching generated-asset digest validation | pending |
| REQ-CIC-1788741692326070-003 | CIC-1788747290653696 | Deterministic Git command-count regression with multiple unrelated task records | pending |
