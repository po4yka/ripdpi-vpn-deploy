---
task_id: ANS-1794231660855533
change: ans-1794231660855533-split-hop-family-egress
commit_sha: 62aff8852b5c11b51ed7ea5f53f240cdcf944d3e
local: passed
local_evidence: "On the PR tree that main now carries as 62aff885: test_split_hop_family_egress, test_transport_audit_network and test_transport_egress_role passed (156), and the related firewall, AWG, cascade, listener and P2 lifecycle modules passed (281). make snapshot-check matched 186 templates. ansible-lint passed on split-hop-ingress, firewall, the two repaired Molecule files and site.yml. Strict OpenSpec validation and the commit hooks passed, including the task contract, secrets coverage, templates-render and deploy-profile tier. This container has no WireGuard module, so the WireGuard native family test ran as a copy with a veth tunnel. That copy passed, and failed for each of three mutants: family scope off, rp_filter=2 absent, and the pre-review policy that lost A-terminated device replies. Molecule images could not be pulled (registry blob 403), so the nginx-xhttp and watchdog scenario repairs were rehearsed with ansible-playbook on localhost: each passed with the change and failed without it. make -k -j 4 check ran as root on 6a1ba88: 11755 passed, and 32 failures sat only in modules this change does not touch (subscription mirror, DHCPv6, Xray log authority, vpnd delivery, tailnet); test_tailnet_management fails identically without the change."
remote_ci: passed
remote_ci_evidence: "PR po4yka/ripdpi-vpn-deploy#550 merged before CI finished on its last head b41877f6, and the CI workflow on main for 62aff885 was cancelled. The ci workflow on main passed on 0a66b0ce20cbd63627db2479ed18820d1634f94e, which carries this change and the live fixes below, including the native lane that runs the WireGuard family test."
dry_run: passed
dry_run_evidence: "Node A dry-runs passed (failed=0) for device-full-staging, split-hop-ingress-staging and split-hop-family-egress-staging on 3e553435, and Node B passed its split-hop-egress-staging dry-run; they previewed the split-hop policy, firewall forwarding/NAT and the IPv4-only gateway. The fixed revision afdd8987 then reached staging without a repeated dry-run by operator decision for staging only; the live rollout keeps a dry-run before every mutation."
staging: passed
staging_evidence: "Disposable UpCloud pair on afdd8987 (deployable digest e40c1a38552ff1ff9d7906babbd6c155da87b3b2b6ce24cc17971c7e9e250c11): Node B split-hop-egress deploy failed=0; Node A ingress and family deploys passed with their promotion proofs; a recipient observed Node B's address for P0, P1 and Hysteria2; AmneziaWG delivered IPv4 through the tunnel with IPv6 refused by policy under awg_ipv6 ipv4-only; with Node B's tunnel stopped every family transport was blocked and no recipient flow left Node A's uplink. Details in Staging acceptance."
live: passed
live_evidence: "Long-lived UpCloud pair. Node B redeployed to 6d099a148ccbcbe46b9f0c0ddaf48b2bbb8152d1 (digest 546ee7e993ee8e4415ef45e60938437fa824d1aa6d0bf3ae746126d94376c9e6), dry-run and deploy failed=0; make verify and make security-verify then passed on both nodes at that revision. Node A was later redeployed for the device lifecycle fixes, each after a failed=0 dry-run, and now runs 0a66b0ce20cbd63627db2479ed18820d1634f94e (digest 36992a79d9dabf971510bdfd8acbbfa31c2e62142b9ccf70b528858ebe29e4ba). make verify was not rerun on Node A at 0a66b0ce. Details in Live acceptance."
client: passed
client_evidence: "Pixel 8 Pro with INCY 3.9.9: a recipient saw Node B for REALITY, XHTTP, Hysteria2 and AmneziaWG through Node A, first with device pixel-8-pro (2026-11-14, Node A at 8c23e141) and again with its replacement pixel-8-pro-2 (2026-11-15, Node A at 0a66b0ce) after pixel-8-pro was revoked. Details in Client acceptance."
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

## Live acceptance

Roles as in staging, on a long-lived pair. Node B runs `vpn-split-hop-egress-live` with the `liveness-sentinel` role on 71354ef069c16773ffc772641d513102ee6b7428 (dry-run and deploy failed=0) and has no service listener; sshd admits port 22 only from Tailnet sources. Node A was onboarded with a `cloud-promotion-intent` as `vpn-split-hop-ingress-live`, then deployed as `vpn-split-hop-family-egress-live` on a76964f4fe807831fe9f6d3204f19bba3efd1fa8 (ok=873, changed=16, failed=0). Liveness policy `awg_ipv6: ipv4-only`, all four profiles required.

- Topology on Node A: `shop0` handshake under two minutes old on both nodes; the `inet split_hop_ingress` table present; one `lookup 200` rule; table 200 is `default dev shop0`; `net.ipv4.conf.shop0.rp_filter` is 2.
- Tunnel up (2026-11-14): Node B's sentinel probed Node A. P0, P1 and Hysteria2 returned `ok` with 204; AmneziaWG returned IPv4 `ok` and IPv6 `policy_refused`. Node A routed two recipient destinations into `shop0`; Node A's uplink carried 0 packets to them and Node B sent 66 packets to them from its own address.
- Failure test: with `wg-quick@shop0` stopped on Node B, all four profiles were `blocked`, and Node A's uplink carried 0 packets to the recipient destinations. Starting the unit again restored a handshake within 32 seconds.
- `make security-verify` passed on both nodes (failed=0). `make verify` on Node B passed its playbook and failed only `source-drift`, because the checkout had moved past Node B's deployed revision. On Node A it failed `P1 public IPv6 hostname resolves through host NSS`, because the P1 name had no AAAA record. Node A now serves a dual-stack P1 name with a DNS-01 certificate and was redeployed on 6d099a148ccbcbe46b9f0c0ddaf48b2bbb8152d1 (ok=858, changed=17, failed=0, proof passed). A first redeploy of Node B to that revision stopped during its dry-run; the second passed its dry-run and deploy (failed=0).
- Live verify (2026-11-14, both nodes at 6d099a148ccbcbe46b9f0c0ddaf48b2bbb8152d1): `make verify` and `make security-verify` passed on Node A and Node B (failed=0).
- Node A later ran 8c23e141c41e8a7accfc396043ab35cca7358921 for the device lifecycle fixes and then 0a66b0ce20cbd63627db2479ed18820d1634f94e (2026-11-15, ok=850, failed=0 after a failed=0 dry-run). Node B still runs 6d099a14, with a `shop0` handshake 79 seconds old when read on 2026-11-15.

## Live findings

- The live Node A profiles used the placeholder `public_site_canonical_url` (fixed in PR po4yka/ripdpi-vpn-deploy#593).
- The deploy precheck refused placeholder certificates of roles a node disables; certificate checks now belong only to `check-certs.sh`, which selects enabled authorities (PR po4yka/ripdpi-vpn-deploy#594).
- The liveness-sentinel AWG inputs were not admitted as deploy extra vars (PR po4yka/ripdpi-vpn-deploy#592).
- `bootstrap-secrets.sh` writes Node A's own origin as the transport canary, which family scope cannot reach, and creates no transport probe identities; the guides now describe both steps.
- UpCloud attaches IPv6 to a second interface, so the live Node A also needs `firewall_awg_uplink6_interface: eth1`.
- A lost controller connection during a deploy left an open protected ingress journal; the documented recovery deploy restored the accepted generation, and the next dry-run and deploy passed.

## Client acceptance

Device: Pixel 8 Pro with INCY 3.9.9, servers imported from `make emit-incy-config` through the link field. The check loads an IP echo page in Chrome on the device and compares the shown address with Node A and Node B on the operator machine, so no address reaches the record.

- 2026-11-14, device `pixel-8-pro` (issue operation 32820372-6155-4e87-a275-550be05e4436), Node A at 8c23e141: REALITY, XHTTP, Hysteria2 and AmneziaWG each connected, and the recipient saw Node B for each. The device's AWG peer on Node A had a handshake 27 seconds old.
- The REALITY and Hysteria2 credentials of `pixel-8-pro` were exposed in an operator session transcript, so the device was revoked. Revocation bf33a5af-0cbf-4cb3-8cb5-a93d6ed489ae stopped on a transient SSH loss, and a fresh revocation de1e7a7e-2d95-4048-94d4-fdc89d6af181 stopped on a source defect (PR po4yka/ripdpi-vpn-deploy#603). After that fix reached Node A, de1e7a7e resumed with its source-rebind approval and reached `complete`; Node A held no match for the exposed REALITY UUID or Hysteria2 password.
- 2026-11-15, device `pixel-8-pro-2` (issue operation 1399c005-ea70-4831-9079-a340dd296ba8), Node A at 0a66b0ce: the four `pixel-8-pro` servers were removed from INCY and the four new ones imported. REALITY, XHTTP, Hysteria2 and AmneziaWG each showed Node B to the recipient; REALITY and Hysteria2 needed a second page load after connecting.

## Client and lifecycle findings

- A staged check of the runtime release returned no link candidates, so a check-mode resume of an interrupted revocation refused with `revocation-candidate-changed` (fixed in PR po4yka/ripdpi-vpn-deploy#603).
- Credential rotation did not reach split-hop ingress nodes, and a source fix could not resume a pending device operation (PR po4yka/ripdpi-vpn-deploy#600); a rebound revocation must renew its intent (PR po4yka/ripdpi-vpn-deploy#602).
- A sentinel generation commit refused the IPv4-only AWG policy refusal (PR po4yka/ripdpi-vpn-deploy#598); Naive retirement on a shared port refused the expected certificate refusal (PR po4yka/ripdpi-vpn-deploy#601).
- Revocation keeps a `revoked` tombstone in `client_registry`, so issuance refuses the same device name with `device-already-exists-in-fleet`. The replacement used a new device name.

## Remaining follow-ups

- Node B's liveness sentinel generation still targets Node A's earlier deployable digest; reinstall it for the current Node A source.
- `make verify` on Node A at 0a66b0ce.
- Orphan release directories on Node B from an interrupted generation.
- A family host still advertises IPv6 to AWG clients (open client-contract change).
