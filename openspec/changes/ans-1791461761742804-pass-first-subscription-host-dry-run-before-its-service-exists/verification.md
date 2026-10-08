---
task_id: ANS-1791461761742804
change: ans-1791461761742804-pass-first-subscription-host-dry-run-before-its-service-exists
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: Exact-role regression uses real role convergence and the authorized fresh permanent P1 without another paid instance.
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
| REQ-SUB-PLANNED-UNIT | ANS-1791461940464917 | Real P1 dry-run refuses vpn-bootstrap.service after simulated template | Reproduced; fix required |
| REQ-SUB-ACTIVATION | ANS-1791461941073032 | Actual role convergence and P1 deploy/verify/security | Required |
| REQ-SUB-DISCOVERY | ANS-1791461940464917 | Loaded, absent, unplanned and error guard tests | Required |
