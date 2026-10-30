---
task_id: SEC-1793385377599445
change: sec-1793385377599445-reality-admission-delivery-repairs
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: Pending an authorized per-node dry-run that previews the rendered maxTimeDiff and probe fingerprint changes.
staging: required
staging_evidence: Pending a staging converge with the 90-second replay window and an authenticated P0 probe.
live: required
live_evidence: Pending an authorized production deploy and verify.
client: required
client_evidence: Pending import of an emitted share URI in a VLESS client and authenticated traffic.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-REALITY-REPLAY-WINDOW | SEC-1793385515086119 | Pending | Required |
| REQ-XRAY-PRODUCTION-PIN | SEC-1793385515749582 | Pending | Required |
| REQ-PROBE-FINGERPRINT | SEC-1793385516458547 | Pending | Required |
| REQ-SHARE-URI | SEC-1793385517096983 | Pending | Required |
| REQ-BUNDLE-TOPOLOGY-TRUTH | SEC-1793385517743702 | Pending | Required |
| REQ-XHTTP-PATH-SECRECY | SEC-1793385518379176 | Pending | Required |
