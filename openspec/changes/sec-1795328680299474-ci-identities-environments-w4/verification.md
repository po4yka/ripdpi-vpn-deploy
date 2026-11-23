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
| REQ-CIID-SEPARATE | SEC-1795328913746423 | SSH revoke drill and SOPS rotation test with historical fixture data key | planned |
| REQ-CIID-ENV-MATRIX | SEC-1795328868236026 | `pytest tests/unit/test_validate_ops_environments.py -k matrix` | planned |
| REQ-CIID-BOOTSTRAP | SEC-1795328902011315 | `pytest tests/unit/test_validate_ops_environments.py -k bootstrap`; ci-bootstrap run receipt with the public halves and the refused-overwrite check; token revocation receipt | planned |
| REQ-CIID-MERGE-GATE | SEC-1795328902011315 | ruleset and environment check receipt; non-owner merge rejection; validator `-k merge_gate` | planned |
| REQ-CIID-MUTATION-TRIGGER | SEC-1795328868236026 | validator `-k trigger`; environment branch policy receipt | planned |
| REQ-CIID-UNTRUSTED-INPUT | SEC-1795328868236026 | Positive typed-toggle test and negative target, pin, endpoint, recipient and revision-change tests before credential access | planned |
| REQ-CIID-LEAST-PRIVILEGE | SEC-1795328913746423 | catalog entries and token scope receipts | planned |
