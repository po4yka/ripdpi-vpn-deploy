---
task_id: SEC-1793428979810694
change: sec-1793428979810694-encrypt-node-side-destination-dns-resolution
commit_sha: 1b1287b8dc7041a2473e259d96bfde4cde47fa44
local: passed
local_evidence: On 1b1287b8 the narrow tests passed (test_transport_egress_kernel, test_transport_destination_boundary, test_transport_egress_role, test_firewall_egress_policy, test_cascade_xray_integration, test_transport_audit_network, test_agent_instructions, test_docs_index: 293 passed; test_resolver_roundtrip and test_runtime_audit_regressions: 51 passed), make snapshot-check reported 168 templates matching, ansible-lint passed on the edited role files, and the native kernel boundary test applied the rendered policy with the new resolver_nat chain in a disconnected namespace. A namespace proof with the production policy, an xray 26.3.27 forwarder as the gateway UID and glibc as the normalizer UID resolved a public name, kept only the public address of a mixed answer, returned no data for a private-only answer, and refused direct normalizer access to the upstream with EPERM. make -k -j 4 check: task-check failed only on a stale board (regenerated; task-check then passed); vpnd-package-check (refuses root), vpnd-test (9), bats-test (sops under the mise HOME) and test-unit (31 of 11091) failed, and every one of those 40 failures reproduces on clean origin/main 3e2e825b in this root container with no IPv6 (41 failures there, none unique to this branch). All pre-commit hooks passed at commit time.
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
| REQ-EGRESS-DNS-FORWARDER | SEC-1793429342091969 | `tests/unit/test_transport_egress_kernel.py`, `tests/unit/test_transport_destination_boundary.py`; native egress fixtures apply the projection in CI | Local passed; CI and deploy evidence required |
| REQ-GATEWAY-DOH-ANSWERS | SEC-1793429343002855 | gateway golden and `tests/unit/test_transport_egress_role.py`; local `xray run -test` plus forwarder probe against a fake upstream | Local passed; CI and deploy evidence required |
| REQ-FRONTEND-DNS-DOH | SEC-1793429343002855 | xray golden and `tests/unit/test_cascade_xray_integration.py` | Local passed; CI and deploy evidence required |
| REQ-HOST-DOT | SEC-1793429343972584 | `tests/unit/test_resolver_roundtrip.py`, `tests/unit/test_firewall_egress_policy.py` | Local passed; CI and deploy evidence required |
| REQ-HOST-DOT-COMPENSATION | SEC-1793429343972584 | `tests/unit/test_resolver_roundtrip.py` failed-proof case | Local passed; CI and deploy evidence required |
| REQ-DNS-MORPH-PORT53 | SEC-1793429343972584 | `tests/unit/test_resolver_roundtrip.py` round trip; kernel render keeps no port-53 listener | Local passed; CI and deploy evidence required |
