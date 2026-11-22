---
task_id: SEC-1795328680299474
change: sec-1795328680299474-ci-identities-environments-w4
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
client: not_applicable
client_evidence: No client-visible change.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-CIID-SEPARATE | SEC-1795328879513998 | Molecule add and revoke; staging revoke drill receipt | planned |
| REQ-CIID-ENV-MATRIX | SEC-1795328868236026 | `pytest tests/unit/test_validate_ops_environments.py -k matrix` | planned |
| REQ-CIID-REVIEWERS | SEC-1795328902011315 | environment check receipt; validator `-k reviewer` | planned |
| REQ-CIID-UNTRUSTED-INPUT | SEC-1795328868236026 | validator `-k pr_input` and `-k ancestor` | planned |
| REQ-CIID-LEAST-PRIVILEGE | SEC-1795328913746423 | catalog entries and token scope receipts | planned |
