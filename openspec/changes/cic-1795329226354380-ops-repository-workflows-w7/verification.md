---
task_id: CIC-1795329226354380
change: cic-1795329226354380-ops-repository-workflows-w7
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
artifact_evidence: Client artifacts are covered by the client gate; no release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OPSWF-REQUEST | CIC-1795329330531652 | `pytest tests/unit/test_validate_ops_request.py` | planned |
| REQ-OPSWF-PREVIEW | CIC-1795329344563256 | staging toggle PR preview run | planned |
| REQ-OPSWF-EXECUTE-ONCE | CIC-1795329358597258 | Merge plan/dry-run with pending changes, conflicting claims, post-effect crash, resume and approved-plan mismatch tests | planned |
| REQ-OPSWF-PREVIEWED-INPUTS | CIC-1795329358597258 | merged request with unpreviewed address change refuses to deploy | planned |
| REQ-OPSWF-SECRETS-IN-CI | CIC-1795329376420274 | Offline issuance and rotation with host access denied, encrypted diff, stdout/stderr and artifact checks, followed by approved staging deployment | planned |
| REQ-OPSWF-CLIENT-ENCRYPTION | CIC-1795329399536234 | `pytest tests/unit/test_encrypt_client_artifact.py`; test client decrypt | planned |
| REQ-OPSWF-SCHEDULED | CIC-1795329376420274 | scheduled run receipts | planned |
| REQ-OPSWF-CLOUD-SESSION | CIC-1795329421913712 | cloud environment review and dispatch test result | planned |
| REQ-OPSWF-RECEIPTS | CIC-1795329439874508 | Branch protection, denied collaborator write and preserved concurrent attempt records | planned |
