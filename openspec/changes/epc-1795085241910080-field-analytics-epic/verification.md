---
task_id: EPC-1795085241910080
change: epc-1795085241910080-field-analytics-epic
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: The epic changes no deploy controller or rendered input; children own that.
staging: required
staging_evidence: null
live: not_applicable
live_evidence: Live rollout is a separate operator decision and is not implied by source closure.
client: required
client_evidence: null
artifact: not_applicable
artifact_evidence: The epic produces no artifact; children own theirs.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-PROGRAM-ORDER | EPC-1795085507364840 | `./taskctl graph` shows the blocked_by edges | planned |
| REQ-PROGRAM-PRIVACY | EPC-1795085507364840 | child verification files name the rejecting tests | planned |
| REQ-PROGRAM-ACCEPT | EPC-1795085548204252 | D7 verification record | planned |
