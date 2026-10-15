---
task_id: ANS-1791996786767919
change: ans-1791996786767919-ingress-egress-commit-window
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: No real inventory or SSH transaction is planned.
staging: not_applicable
staging_evidence: Source and native validation does not establish a staging rollout.
live: not_applicable
live_evidence: No production deployment is planned.
client: not_applicable
client_evidence: No client payload changes.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OPS-ORP-COMMIT-ATOMIC | ANS-1791996824479999 | SIGKILL cases at each commit boundary in the site transaction harness and native lane | pending |
