---
task_id: XRY-1793635470456809
change: xhttp-payload-tcp-reserve
commit_sha: null
local: required
local_evidence: Baseline exporter tests passed, 120 tests. Changed-input checks are pending.
remote_ci: required
remote_ci_evidence: Run the selected checks on both PR heads.
dry_run: not_applicable
dry_run_evidence: Source and local test changes only.
staging: not_applicable
staging_evidence: No staging rollout is included.
live: not_applicable
live_evidence: No live host or credential action is included.
client: required
client_evidence: Paired parser, persistence, native pool and payload selector checks are pending. Physical-device and filtered-network acceptance are outside this change.
artifact: required
artifact_evidence: Compare the emitted synthetic fixture with the paired consumer bytes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-XHTTP-RECIPIENT-POOL | XRY-1793635898207050 | Exporter and paired consumer gates pending | Required |
| REQ-FAILOVER-TCP-RESERVE | XRY-1793635898207050 | Mixed emitted fixture and paired payload selection gates pending | Required |
