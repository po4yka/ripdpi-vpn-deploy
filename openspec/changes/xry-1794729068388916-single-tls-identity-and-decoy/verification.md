---
task_id: XRY-1794729068388916
change: xry-1794729068388916-single-tls-identity-and-decoy
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
client_evidence: No client payload changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-TMD-SELF-STEAL-OWNED-DECOY | XRY-1794729166198238 | Self-steal Molecule cases for the production refusal and the operator tree | required |
| REQ-PROTO-RTV-NETWORK | XRY-1794729177636809 | Validator unit tests for the four report values with a stub ASN lookup | required |
| REQ-TMD-SINGLE-IDENTITY | XRY-1794729177636809 | Preflight tests for the refusal, the shared-certificate pass and the recorded exception | required |
| REQ-TMD-PORT-80-DECOY | XRY-1794729189657998 | nginx-xhttp snapshot and Molecule requests on port 80 | required |
