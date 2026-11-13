---
task_id: ANS-1794231660855533
change: ans-1794231660855533-split-hop-family-egress
commit_sha: 62aff8852b5c11b51ed7ea5f53f240cdcf944d3e
local: passed
local_evidence: "On the PR tree that main now carries as 62aff885: test_split_hop_family_egress, test_transport_audit_network and test_transport_egress_role passed (156), and the related firewall, AWG, cascade, listener and P2 lifecycle modules passed (281). make snapshot-check matched 186 templates. ansible-lint passed on split-hop-ingress, firewall, the two repaired Molecule files and site.yml. Strict OpenSpec validation and the commit hooks passed, including the task contract, secrets coverage, templates-render and deploy-profile tier. This container has no WireGuard module, so the WireGuard native family test ran as a copy with a veth tunnel. That copy passed, and failed for each of three mutants: family scope off, rp_filter=2 absent, and the pre-review policy that lost A-terminated device replies. Molecule images could not be pulled (registry blob 403), so the nginx-xhttp and watchdog scenario repairs were rehearsed with ansible-playbook on localhost: each passed with the change and failed without it. make -k -j 4 check ran as root on 6a1ba88: 11755 passed, and 32 failures sat only in modules this change does not touch (subscription mirror, DHCPv6, Xray log authority, vpnd delivery, tailnet); test_tailnet_management fails identically without the change."
remote_ci: required
remote_ci_evidence: "PR po4yka/ripdpi-vpn-deploy#550 merged before CI finished on its last head b41877f6, so its Molecule and native lanes were cancelled. Earlier heads failed only on the staging-profile parity test (fixed in c75c2ae1) and on the nginx-xhttp Molecule regression inherited from a34903d9 (fixed in 62aff885). The CI workflow on main for 62aff885 was still pending when this was recorded; it must pass, including the native lane that runs the WireGuard family test."
dry_run: passed
dry_run_evidence: "Node A dry-runs passed (failed=0) for device-full-staging, split-hop-ingress-staging and split-hop-family-egress-staging on 3e553435, and Node B passed its split-hop-egress-staging dry-run; they previewed the split-hop policy, firewall forwarding/NAT and the IPv4-only gateway. The fixed revision afdd8987 then reached staging without a repeated dry-run by operator decision for staging only; the live rollout keeps a dry-run before every mutation."
staging: passed
staging_evidence: "Disposable UpCloud pair on afdd8987 (deployable digest e40c1a38552ff1ff9d7906babbd6c155da87b3b2b6ce24cc17971c7e9e250c11): Node B split-hop-egress deploy failed=0; Node A ingress and family deploys passed with their promotion proofs; a recipient observed Node B's address for P0, P1 and Hysteria2; AmneziaWG delivered IPv4 through the tunnel with IPv6 refused by policy under awg_ipv6 ipv4-only; with Node B's tunnel stopped every family transport was blocked and no recipient flow left Node A's uplink. Details in Staging acceptance."
live: required
live_evidence: Pending an authorized deploy of a family host; the selector stays false in every committed profile.
client: required
client_evidence: "Pending authenticated Pixel 8 Pro traffic over each family transport through a family Node A, with one standard-path identity per device."
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
| REQ-SHF-COEXIST | ANS-1794550099725815 | Molecule `split-hop-ingress` loads the ingress-only and family policies and admits each ruleset through `transport_egress_kernel.audit_authority` (fails on the old template with `unsupported-postrouting-authority`); `test_split_hop_native.py::test_family_scope_sends_recipient_and_device_egress_only_through_b` asserts a tunnel-sized MSS at the recipient for gateway and device flows (MSS 1448 against 1380 without the clamp); `make snapshot-check` | Passed |
| REQ-SHF-LIVENESS | ANS-1794558129615458 | `test_protocol_liveness_sentinel.py::test_awg_ipv6_policy_refusal_is_distinct_from_network_failure` (all-`Permission denied` IPv6 attempts become `policy_refused` with tunnel proof; a mixed reset stays `network`); `test_protocol_liveness.py::test_awg_ipv6_refusal_counts_only_under_an_ipv4_only_policy` and `::test_schema_rejects_an_unknown_awg_ipv6_mode`; staging showed the family IPv6 refusal as curl `Permission denied` on every IPv6 address | Passed |

## Staging acceptance

Roles: Node A is the ingress responder and family host; Node B is the egress initiator with no public listeners. Source afdd89876bb7402e226ed697956ff53443694637, deployable digest e40c1a38552ff1ff9d7906babbd6c155da87b3b2b6ce24cc17971c7e9e250c11, liveness policy `awg_ipv6: ipv4-only`.

- Topology on Node A: `wg show shop0` showed Node B as the endpoint with a handshake seconds old; Node B showed Node A on UDP 51821 with a 25-second keepalive. The `inet split_hop_ingress` table limited the ingress-only scope to UIDs 971 and 972 before the family converge; `ip rule` sent fwmark 0x1 to table 200, whose default route is `shop0`; `net.ipv4.conf.shop0.rp_filter` was 2.
- Tunnel up: P0, P1 and Hysteria2 probes passed; Node B sent 56 packets from its own address to the recipient destinations that Node A routed into `shop0`. AmneziaWG reported IPv4 `ok` through the tunnel, IPv6 `policy_refused` (curl `Permission denied` on every IPv6 address) and a fresh handshake on three consecutive runs. Node A's uplink carried only its own system resolver's DNS-over-TLS (TCP 853) to those destinations.
- Failure test: with `wg-quick@shop0` stopped on Node B, all four profiles were `blocked`, Node B sent nothing, and Node A's uplink showed no packet to the probe's recipients (only the system resolver and `tailscaled` control traffic). Restarting the unit restored a fresh handshake within 30 seconds.
- The single-shot promotion proof also failed on some deploys when the operator uplink dropped UDP; those deploys had converged, and the ingress and family deploys above passed their proofs.
- Cleanup: guarded destroys of Node A, Node B and the operator exit node each recorded `verified` provider absence; Node A was de-onboarded and its executor profile deleted; the three tailnet devices were removed; the peer-relay, exit-node and SSH grants, the exit tag owner and the exit-node auto-approver were removed from the tailnet policy.

## Staging findings

- The split-hop MSS clamp in POSTROUTING made the transport-egress kernel audit refuse every apply, verify and rollback on Node A (fixed in PR po4yka/ripdpi-vpn-deploy#586, REQ-SHF-COEXIST).
- Protocol liveness required dual-stack AWG, which a family host refuses by design (fixed in PR po4yka/ripdpi-vpn-deploy#587, REQ-SHF-LIVENESS). A family host still advertises IPv6 to AWG clients; that client-contract change is open.
- An operator path through a Tailscale exit node needs a 1420 MTU for QUIC and staging nodes outside the exit node's subnet; behind hard NAT, management SSH needs a peer relay instead of DERP.
- The one-shot executor's six-hour window must cover the whole rollout, and its AWG toolchain digest differs between provisionings, so a liveness configuration must take its runtime pins from the provisioned executor.
- The executor's detached install job failed intermittently under systemd while the same engine committed when run as root; the installer waits about 11 minutes before it reports `installation-unknown-pending-preserved`.
- De-onboarding after a cleanup-manifest reissue needs the bound and reissued manifests in the environment.

## Remaining acceptance blockers

- Live: an authorized dry-run and deploy of a family host with `make verify` and `make security-verify`.
- Client: the Pixel 8 Pro check above.
