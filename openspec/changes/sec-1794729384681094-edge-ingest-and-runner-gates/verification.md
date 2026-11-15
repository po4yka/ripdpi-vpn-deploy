---
task_id: SEC-1794729384681094
change: sec-1794729384681094-edge-ingest-and-runner-gates
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: The policy, workflow and test changes have no host effect; the relay change reaches the existing collector through the ordinary deploy transaction.
live: required
live_evidence: null
client: not_applicable
client_evidence: No client payload changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SEC-EIG-EDGE-FIREWALL | SEC-1794729475212458 | Rego tests for the existing-server denial, the creation pass and the missing-firewall denials | required |
| REQ-SEC-EIG-RELAY-LIMITS | SEC-1794729504775329 | Relay snapshot, promtool cases and a Molecule push over the limit | required |
| REQ-SEC-EIG-RUNNER-LANE | SEC-1794729526950019 | Workflow policy unit test; `configure-repository.py` check test; publish workflow trigger test | required |
| REQ-SEC-EIG-AGENT-SETTINGS | SEC-1794729547422604 | Agent instructions unit test with accept and reject cases | required |
