---
task_id: SEC-1793428979810694
change: sec-1793428979810694-encrypt-node-side-destination-dns-resolution
commit_sha: c67006791f2b9b405c9e3b2e435912e6c9c3ad18
local: passed
local_evidence: On c67006791f2b9b405c9e3b2e435912e6c9c3ad18 (main merged with SEC-1793428673775693's forwarder; this change narrowed to the host DoT drop-in and strict 853) the affected tests passed: test_resolver_roundtrip, test_runtime_audit_regressions, test_firewall_egress_policy, test_transport_egress_role, test_transport_egress_kernel, test_transport_destination_boundary, test_cascade_xray_integration, test_agent_instructions, test_docs_index, test_transport_audit_network (345 passed); make snapshot-check reported 168 templates matching; taskctl validate and strict OpenSpec validation passed. Earlier evidence on 1b1287b8 (pre-merge, with the since-dropped NAT forwarder): 293 + 51 unit tests, the native kernel boundary test and a namespace proof passed; make -k -j 4 check failures (40) all reproduced on clean main in this root container.
remote_ci: required
remote_ci_evidence: Pending PR CI on the exact head SHA, including the native egress and kernel lanes.
dry_run: required
dry_run_evidence: Pending an authorized per-node dry-run that previews the forwarder policy, gateway configs and the resolved drop-in.
staging: required
staging_evidence: Pending a staging converge with an authenticated recipient lookup and no plaintext port-53 egress in a capture on the uplink.
live: required
live_evidence: Pending an authorized production deploy and verify.
client: required
client_evidence: Pending authenticated device traffic to a named destination through the staged node.
artifact: required
artifact_evidence: Snapshot goldens, the egress reference and role notes were updated; PR review pending.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-HOST-DOT | SEC-1793429343972584 | `tests/unit/test_resolver_roundtrip.py` (drop-in installed once, proof call, idempotence), `tests/unit/test_firewall_egress_policy.py` (strict 853) | Local passed; CI and deploy evidence required |
| REQ-HOST-DOT-COMPENSATION | SEC-1793429343972584 | `tests/unit/test_resolver_roundtrip.py` failed-proof case (drop-in withdrawn, second restart, categorical failure) | Local passed; CI and deploy evidence required |
| REQ-DNS-MORPH-PORT53 | SEC-1793429343972584 | `tests/unit/test_resolver_roundtrip.py` round trip and `tests/unit/test_runtime_audit_regressions.py` resolver states | Local passed; CI and deploy evidence required |
| (superseded) recipient forwarder | SEC-1793429342091969, SEC-1793429343002855 | NAT-redirect forwarder built and proven locally, then dropped on merge of SEC-1793428673775693 (main's `127.0.0.2` forwarder) | Superseded; not part of the merged tree |
