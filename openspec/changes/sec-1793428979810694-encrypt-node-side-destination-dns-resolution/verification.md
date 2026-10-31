---
task_id: SEC-1793428979810694
change: sec-1793428979810694-encrypt-node-side-destination-dns-resolution
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
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-EGRESS-DNS-FORWARDER | SEC-1793429342091969 | `tests/unit/test_transport_egress_kernel.py`, `tests/unit/test_transport_destination_boundary.py`; native egress fixtures apply the projection in CI | Pending |
| REQ-GATEWAY-DOH-ANSWERS | SEC-1793429343002855 | gateway golden and `tests/unit/test_transport_egress_role.py`; local `xray run -test` plus forwarder probe against a fake upstream | Pending |
| REQ-FRONTEND-DNS-DOH | SEC-1793429343002855 | xray golden and `tests/unit/test_cascade_xray_integration.py` | Pending |
| REQ-HOST-DOT | SEC-1793429343972584 | `tests/unit/test_resolver_roundtrip.py`, `tests/unit/test_firewall_egress_policy.py` | Pending |
| REQ-HOST-DOT-COMPENSATION | SEC-1793429343972584 | `tests/unit/test_resolver_roundtrip.py` failed-proof case | Pending |
| REQ-DNS-MORPH-PORT53 | SEC-1793429343972584 | `tests/unit/test_resolver_roundtrip.py` round trip; kernel render keeps no port-53 listener | Pending |
