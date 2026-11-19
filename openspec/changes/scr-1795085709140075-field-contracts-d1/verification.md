---
task_id: SCR-1795085709140075
change: scr-1795085709140075-field-contracts-d1
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: No deploy controller or rendered deployment input changes.
staging: not_applicable
staging_evidence: Contract-only change; staging proof is owned by D7.
live: not_applicable
live_evidence: Contract-only change; no live system is affected.
client: required
client_evidence: null
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-REPORT-SHAPE | SCR-1795085965580974 | `tests/unit/test_bundle_schema.py` golden and extra-property cases | planned |
| REQ-REPORT-BUCKET | SCR-1795085995858987 | `tests/unit/test_bundle_schema.py` stage-pairing cases | planned |
| REQ-REPORT-PRIVACY | SCR-1795085995858987 | `contract/negative/` identifier and timestamp cases | planned |
| REQ-REPORT-MINBUCKET | SCR-1795085995858987 | attempts-below-5 negative fixture | planned |
| REQ-BUNDLE-V3 | SCR-1795086029049140 | v2 rejection and http endpoint negative cases | planned |
| REQ-BUNDLE-HEALTH-TTL | SCR-1795086060772476 | expired-health fixture and documentation check | planned |
