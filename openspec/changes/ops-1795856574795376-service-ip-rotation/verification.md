---
task_id: OPS-1795856574795376
change: ops-1795856574795376-service-ip-rotation
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: not_applicable
live_evidence: Rotating a production node is a separate operator decision.
client: required
client_evidence: null
artifact: not_applicable
artifact_evidence: No release artifact is produced.
---
# Verification

Local evidence covers plan shape, inventory rendering, guest `/32` lifecycle and consumer selection. Provider attach timing, provider-edge delivery to the new address and device refresh from filtered networks need staging and client evidence.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SIP-GENERATIONS | OPS-1795857751222463 | `make tf-test`: three `service_ipv4_*` runs per provider root | required |
| REQ-SIP-SPLIT | OPS-1795857809017056 | `tests/unit/test_render_inventory.py`, `test_fleet_inspection.py`, vpnd runner tests | required |
| REQ-SIP-GUEST | OPS-1795858050569373 | `make molecule-test ROLE=baseline` attach, retire and clear sequence | required |
| REQ-SIP-POLICY | OPS-1795857932939870 | `make tf-policy-verify` | required |
