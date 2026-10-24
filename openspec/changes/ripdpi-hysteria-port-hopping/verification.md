---
task_id: OPS-1792820562787120
change: ripdpi-hysteria-port-hopping
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: No runtime or provider change.
staging: not_applicable
staging_evidence: No staging resource mutation in this source delivery.
live: not_applicable
live_evidence: No fleet deployment or live credential action authorized.
client: required
client_evidence: null
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-AUDIT-HY-COMPATIBILITY | OPS-1792820856126759 | Targeted recipient payload tests and full local gate | required |
| REQ-AUDIT-HY-COMPATIBILITY | OPS-1792820857234441 | Paired client real-server hopping, IPv6, Salamander and import tests | required |
| REQ-DR-HOPPING-ADMISSION | OPS-1792820856126759 | Positive policy parity and atomic failure tests | required |
| REQ-DR-HOPPING-ADMISSION | OPS-1792820858662402 | Exact producer and client PR and main terminal hosted checks | required |

## Current source evidence

- Targeted recipient hopping, payload boundary, bundle schema, transport semantics, host selection and Hysteria audit tests: 307 passed.
- Documentation checks: 10 passed. The generated hopping bundle passed semantic validation.
- Task contracts and strict OpenSpec validation passed. Independent source review found no code defect.
- The full local check was canceled while still queued at the shared build gate; it did not start and remains required.
- Source review identified the paired client qualification as a release precondition. Keep this producer change local until the client passes the real peer matrix and reaches main. No client, artifact or hosted completion is claimed here.
