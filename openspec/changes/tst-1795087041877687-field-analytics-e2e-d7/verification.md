---
task_id: TST-1795087041877687
change: tst-1795087041877687-field-analytics-e2e-d7
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: No deploy controller or rendered input change.
staging: required
staging_evidence: null
live: not_applicable
live_evidence: Production is out of scope.
client: required
client_evidence: null
artifact: not_applicable
artifact_evidence: The evidence is in the verification file; no release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-E2E-CLASSIFY | TST-1795087099844740 | DROP and RST client report buckets | planned |
| REQ-E2E-INGEST | TST-1795087099844740 | staging Prometheus query output | planned |
| REQ-E2E-ALERT | TST-1795087099844740 | Alertmanager active alert | planned |
| REQ-E2E-BUNDLE | TST-1795087099844740 | generated bundle validated as v3 | planned |
| REQ-E2E-FAILOVER | TST-1795087151868733 | client logs and traffic observation before and after unblock | planned |
