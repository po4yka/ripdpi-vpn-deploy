---
task_id: SCR-1795086521848661
change: scr-1795086521848661-bundle-v3-generation-d4
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: Staging proof of the generated bundle is owned by D7.
live: not_applicable
live_evidence: Rolling v3 bundles to production is a separate operator decision.
client: required
client_evidence: null
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-GEN-V3 | SCR-1795086544436996 | `tests/unit/test_bundle_schema.py` validates generator output as v3 | planned |
| REQ-GEN-HEALTH | SCR-1795086565223483 | unit test with down, healthy and no-input liveness fixtures | planned |
| REQ-GEN-TTL | SCR-1795086565223483 | unit test with ttl above the maximum | planned |
| REQ-GEN-FIELDREPORT | SCR-1795086581871015 | unit test with field reports disabled | planned |
| REQ-GEN-COHORT-ROTATE | SCR-1795086600479731 | unit test of rotation overlap and a log search for the token | planned |
