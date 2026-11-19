---
task_id: MON-1795086646495369
change: mon-1795086646495369-network-block-detection-d5
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: No deploy controller change; fleet-rotate hint is read-only.
staging: required
staging_evidence: null
live: not_applicable
live_evidence: Enabling on production is a separate operator decision.
client: required
client_evidence: null
artifact: not_applicable
artifact_evidence: No release artifact is produced.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-BLOCK-ALERT | MON-1795086667788936 | promtool divergence case | planned |
| REQ-BLOCK-NOT-SERVER | MON-1795086687652889 | promtool server-down case | planned |
| REQ-BLOCK-LOWSAMPLE | MON-1795086687652889 | promtool low-sample case | planned |
| REQ-BLOCK-HINT | MON-1795086713751110 | unit test: PLAN shows the hint and starts nothing | planned |
| REQ-BLOCK-RUNBOOK | MON-1795086734829714 | annotation and anchor tests in tests/unit/test_observability_control_plane_alerting.py | planned |
