---
task_id: ANS-1794729221714172
change: ans-1794729221714172-awg-per-instance-wire-shape
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: required
client_evidence: null
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROTO-AWG-SHAPE-GENERATED | ANS-1794729302489703 | Generator unit tests for bounds, relationships and the degenerate redraw | required |
| REQ-PROTO-AWG-SHAPE-EXPLICIT | ANS-1794729302489703 | Secrets validation tests for the production refusals and the staging pass | required |
| REQ-PROTO-AWG-SHAPE-HEADERS | ANS-1794729321608732 | AmneziaWG Molecule and task tests for the widened guard and the measurement exception | required |
| REQ-PROTO-AWG-SHAPE-PORT | ANS-1794729336937986 | Secrets validation test for the default port; provider `tftest` cases for the legacy list and the contract | required |
