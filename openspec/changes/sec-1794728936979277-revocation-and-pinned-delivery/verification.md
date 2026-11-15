---
task_id: SEC-1794728936979277
change: sec-1794728936979277-revocation-and-pinned-delivery
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
client_evidence: No client payload format changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SEC-RPD-ROLLBACK-REVOCATION | SEC-1794728996747903 | Rollback unit tests for the removed-client refusal and the equal-set pass | required |
| REQ-SEC-RPD-SHARE-REVOCATION | SEC-1794729007676570 | Subscription-host Molecule cases for a revoked token and an undeclared bundle | required |
| REQ-SEC-RPD-PINNED-PAYLOAD-SSH | SEC-1794729019627773 | Issuance tests with a stub `ssh` that records its arguments | required |
| REQ-SEC-RPD-MIRROR-IDENTITY | SEC-1794729019627773 | Subscription-host Molecule cases for the missing host key and the denied read | required |
| REQ-SEC-RPD-DATA-KEY-ROTATION | SEC-1794729031539704 | Rotation script tests with a stub `sops`, including the failure path | required |
