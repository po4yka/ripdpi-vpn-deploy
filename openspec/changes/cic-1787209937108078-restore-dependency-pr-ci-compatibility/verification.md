---
task_id: CIC-1787209937108078
change: cic-1787209937108078-restore-dependency-pr-ci-compatibility
commit_sha: null
local: required
local_evidence: pending
remote_ci: required
remote_ci_evidence: pending
dry_run: not_applicable
dry_run_evidence: CI-only change; no infrastructure plan is changed.
staging: not_applicable
staging_evidence: CI-only change; no staging deployment is authorized.
live: not_applicable
live_evidence: CI-only change; no live deployment is authorized.
client: not_applicable
client_evidence: No client-facing behavior changes.
artifact: required
artifact_evidence: Pending immutable image digest and its scan record.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-CIC-1787209937108078-001 | CIC-1787209937108079 | pinned taskctl validation and hosted task-contract job | pending |
| REQ-CIC-1787209937108078-002 | CIC-1787209937108080 | published digest and Trivy HIGH,CRITICAL scan | pending |
