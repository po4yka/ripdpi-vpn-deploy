---
task_id: VPD-1787497073989478
change: vpd-1787497073989478-vpnd-share-bundle-hardening
commit_sha: null
local: required
local_evidence: ""
remote_ci: required
remote_ci_evidence: ""
dry_run: not_applicable
dry_run_evidence: no Terraform surface
staging: not_applicable
staging_evidence: covered by local tests and CI cargo suite
live: not_applicable
live_evidence: no deployed-state dependency
client: not_applicable
client_evidence: bundle consumers see unchanged URL shapes
artifact: not_applicable
artifact_evidence: no artifact contracts affected
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SHARE-TOKEN-VALIDITY | VPD-1787497123361827 | Targeted tests for empty and whitespace tokens via stdin and token file | Pending |
| REQ-SHARE-HOST-RESOLUTION | VPD-1787497123379234 | Regression test asserting nonzero exit and named key when server_name absent | Pending |
| REQ-SHARE-BUNDLE-PERMS | VPD-1787497123396516 | Tests asserting 0600 on all bundle files incl QR, stale-temp re-run success, and cleanup on failure | Pending |
