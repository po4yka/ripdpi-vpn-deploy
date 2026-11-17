---
task_id: MON-1794937115554282
change: mon-1794937115554282-deploy-coverage-silence
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: The observability collector and silence gateway exist only on the fleet; staging has no gateway to receive the silence.
live: required
live_evidence: null
client: not_applicable
client_evidence: No client payload or device artifact changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OPS-DEPLOY-SILENCE-SCOPE | MON-1794937405270339 | Pending | Pending |
| REQ-OPS-DEPLOY-SILENCE-LIFECYCLE | MON-1794937362082306 | Pending | Pending |
| REQ-OPS-DEPLOY-SILENCE-FAILURE | MON-1794937405270339 | Pending | Pending |
| REQ-OPS-DEPLOY-SILENCE-AUTHORITY | MON-1794937362082306 | Pending | Pending |
