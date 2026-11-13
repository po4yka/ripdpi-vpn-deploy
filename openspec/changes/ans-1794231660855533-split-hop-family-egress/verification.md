---
task_id: ANS-1794231660855533
change: ans-1794231660855533-split-hop-family-egress
commit_sha: 62aff8852b5c11b51ed7ea5f53f240cdcf944d3e
local: passed
local_evidence: "On the PR tree that main now carries as 62aff885: test_split_hop_family_egress, test_transport_audit_network and test_transport_egress_role passed (156), and the related firewall, AWG, cascade, listener and P2 lifecycle modules passed (281). make snapshot-check matched 186 templates. ansible-lint passed on split-hop-ingress, firewall, the two repaired Molecule files and site.yml. Strict OpenSpec validation and the commit hooks passed, including the task contract, secrets coverage, templates-render and deploy-profile tier. This container has no WireGuard module, so the WireGuard native family test ran as a copy with a veth tunnel. That copy passed, and failed for each of three mutants: family scope off, rp_filter=2 absent, and the pre-review policy that lost A-terminated device replies. Molecule images could not be pulled (registry blob 403), so the nginx-xhttp and watchdog scenario repairs were rehearsed with ansible-playbook on localhost: each passed with the change and failed without it. make -k -j 4 check ran as root on 6a1ba88: 11755 passed, and 32 failures sat only in modules this change does not touch (subscription mirror, DHCPv6, Xray log authority, vpnd delivery, tailnet); test_tailnet_management fails identically without the change."
remote_ci: required
remote_ci_evidence: "PR po4yka/ripdpi-vpn-deploy#550 merged before CI finished on its last head b41877f6, so its Molecule and native lanes were cancelled. Earlier heads failed only on the staging-profile parity test (fixed in c75c2ae1) and on the nginx-xhttp Molecule regression inherited from a34903d9 (fixed in 62aff885). The CI workflow on main for 62aff885 was still pending when this was recorded; it must pass, including the native lane that runs the WireGuard family test."
dry_run: required
dry_run_evidence: Pending an authorized Node A dry-run with split_hop_family_egress enabled that previews the split-hop policy, firewall forwarding/NAT and the IPv4-only gateway configuration.
staging: required
staging_evidence: Pending a staging Node A/Node B pair where a recipient observes Node B's address for P0, P1, Hysteria2 and AmneziaWG, and a stopped tunnel leaves no recipient flow on Node A's uplink capture.
live: required
live_evidence: Pending an authorized deploy of a family host; the selector stays false in every committed profile.
client: required
client_evidence: Pending authenticated device traffic over each family transport through the staged Node A.
artifact: passed
artifact_evidence: "Merged to main as 62aff885 through PR po4yka/ripdpi-vpn-deploy#550: split-hop-ingress, firewall and transport-egress templates and goldens, the site.yml guard and boundary ordering, decision 0003, the split-hop pilot guide and the role notes."
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SHF-ROUTE | ANS-1794232229453495 | `test_split_hop_native.py::test_family_scope_sends_recipient_and_device_egress_only_through_b` (veth copy locally; WireGuard in the main CI native lane) | Passed locally; CI pending |
| REQ-SHF-FAIL-CLOSED | ANS-1794232364807121 | Native family test (stopped tunnel, A-terminated device flow); `test_transport_audit_network.py::test_family_scope_moves_device_forwarding_and_guard_onto_the_tunnel` | Passed locally; CI pending |
| REQ-SHF-IPV4 | ANS-1794232503959033 | `test_transport_egress_role.py::test_split_hop_family_scope_keeps_direct_gateway_on_ipv4` | Passed |
| REQ-SHF-ADMISSION | ANS-1794232503959033 | `test_split_hop_family_egress.py` (guard, identity parsing, boundary before activation); `make snapshot-check` | Passed |
| REQ-SHF-ROUTE | ANS-1794550099725815 | Molecule `split-hop-ingress` loads the ingress-only and family policies and admits each ruleset through `transport_egress_kernel.audit_authority` (fails on the old template with `unsupported-postrouting-authority`); `test_split_hop_native.py::test_family_scope_sends_recipient_and_device_egress_only_through_b` asserts a tunnel-sized MSS at the recipient for gateway and device flows (MSS 1448 against 1380 without the clamp); `make snapshot-check` | Passed |
