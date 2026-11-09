---
task_id: ANS-1794231660855533
change: ans-1794231660855533-split-hop-family-egress
commit_sha: null
local: required
local_evidence: Pending the final local run on the committed head.
remote_ci: required
remote_ci_evidence: Pending PR CI on the exact head SHA, including the native lane that runs the WireGuard family test.
dry_run: required
dry_run_evidence: Pending an authorized Node A dry-run with split_hop_family_egress enabled that previews the split-hop policy, firewall forwarding/NAT and the IPv4-only gateway configuration.
staging: required
staging_evidence: Pending a staging Node A/Node B pair where a recipient observes Node B's address for P0, P1, Hysteria2 and AmneziaWG, and a stopped tunnel leaves no recipient flow on Node A's uplink capture.
live: required
live_evidence: Pending an authorized deploy of a family host; the selector stays false in every committed profile.
client: required
client_evidence: Pending authenticated device traffic over each family transport through the staged Node A.
artifact: required
artifact_evidence: Snapshot goldens, decision 0003, the pilot guide and role notes updated in this change; PR review pending.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SHF-ROUTE | ANS-1794232229453495 | `test_split_hop_native.py::test_family_scope_sends_recipient_and_device_egress_only_through_b` | Pending |
| REQ-SHF-FAIL-CLOSED | ANS-1794232364807121 | Native family test (stopped tunnel); `test_transport_audit_network.py::test_family_scope_moves_device_forwarding_and_guard_onto_the_tunnel` | Pending |
| REQ-SHF-IPV4 | ANS-1794232503959033 | `test_transport_egress_role.py::test_split_hop_family_scope_keeps_direct_gateway_on_ipv4` | Pending |
| REQ-SHF-ADMISSION | ANS-1794232503959033 | `test_split_hop_family_egress.py`; `make snapshot-check` | Pending |
