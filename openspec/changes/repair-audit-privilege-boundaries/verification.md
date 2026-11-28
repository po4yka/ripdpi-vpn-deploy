---
task_id: SEC-1795869545417758
change: repair-audit-privilege-boundaries
commit_sha: null
local: required
local_evidence: Focused pytest suites, vpnd parity and lint, bootstrap Bats, Conftest, template snapshots and native nginx smoke test passed.
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: Offline tests and role renders cover the source changes.
staging: not_applicable
staging_evidence: This source change does not request staging deployment.
live: not_applicable
live_evidence: This source change does not request fleet deployment.
client: not_applicable
client_evidence: Export tests cover the bundle tag and QR payload.
artifact: not_applicable
artifact_evidence: No release artifact is required for this source change.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-AUDIT-REALM | SEC-1795869608593228 | Service sandbox tests and template snapshots | Passed locally |
| REQ-AUDIT-PRIVACY | SEC-1795869608593228 | Native nginx internal redirects, AWG bundle tests, and vpnd explain tests | Passed locally |
| REQ-AUDIT-INPUT | SEC-1795869608593228 | Operator and subscription tests, provider policy tests, and Terraform format check | Passed locally |
| REQ-AUDIT-OPERATOR | SEC-1795869608593228 | Bootstrap Bats, vpnd parity and CI selection tests | Passed locally |
