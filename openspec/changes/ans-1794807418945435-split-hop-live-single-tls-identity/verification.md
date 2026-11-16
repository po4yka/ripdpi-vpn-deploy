---
task_id: ANS-1794807418945435
change: ans-1794807418945435-split-hop-live-single-tls-identity
commit_sha: c7706de571a8c43eefde9d7a8a124ea9a35c25c8
local: passed
local_evidence: "On the working tree of the change, based on 11b50083: pytest for test_tls_identity_preflight.py, test_deploy_profile_guard.py, test_reality_self_steal.py and the profile tests test_split_hop_live_node_a_keeps_the_production_device_transports, test_committed_profiles_carry_only_the_neutral_placeholder_origin and test_disposable_staging_profiles_serve_the_generated_masquerade_origin: 64 passed, exit 0. scripts/check-deploy-profile.py exit 0. Not run: make check, Molecule and the snapshot suite (no template or role changed)."
remote_ci: passed
remote_ci_evidence: "CI run 43812776555 on main at 441c02b4 (the merge of this change) completed with success."
dry_run: passed
dry_run_evidence: "On 2026-11-16 the full dry-run of the live Node A at 441c02b4 exited 0 with 20 changed, 0 failed and 0 unreachable: firewall publication, transport-egress candidates, Xray configuration, the self-steal candidate scaffold, the nginx candidate, the Hysteria validator, removal of the bundled model news units, AmneziaWG runtime and firewall, watchdog files and the node manifest. An earlier dry-run of the same tree from the pull request commit had also exited 0. Check mode opens no nginx site journal, so it did not show the refusal recorded under live."
staging: not_applicable
staging_evidence: The staging profiles do not change, and the changed profile is used only by the live pair.
live: passed
live_evidence: "On 2026-11-16 the live Node A was deployed at 441c02b4 (deployable digest bb1c786578ee): deploy exit 0 with 30 changed and 0 failed, then make verify, source-drift and security-verify exit 0. The node manifest records no TLS identity exception. An outside scan showed one certificate on TCP/443 with and without SNI, on TCP/8443 and on QUIC/443, the operator site on both HTTPS ports, and the self-steal endpoint bound to loopback only. The liveness sentinel on Node B was reinstalled from 441c02b4 for the new Node A identity, and scripts/sshd-promotion-proof.py returned status passed for that identity. A first deploy attempt failed at the nginx-xhttp publication, because the site journal admitted only the bundled page paths for nginx-xhttp and the first operator site used other names; the protected stage restored the accepted generation. That defect is fixed by ANS-1794811064145966. The deploy that passed used an operator site with the admitted paths."
client: required
client_evidence: "Partly done on 2026-11-16. The device-lifecycle refresh of the one device on the live Node A completed (1 node written, 1 adopted), and its native probes accepted all four credential profiles. In the new delivery the REALITY and AmneziaWG entries changed; the XHTTP and Hysteria2 entries are byte-identical to the previous delivery. Pending: import of the two changed entries on the device and one handshake for each transport from it."
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SHL-SELF-STEAL-IDENTITY | ANS-1794807559120996 | `test_committed_profiles_that_need_a_layout_change_or_an_exception_on_production` runs the real preflight task for every committed profile: the live family-egress profile now passes and the other three split-hop Node A profiles still refuse; `test_split_hop_live_node_a_keeps_the_production_device_transports` pins the profile to the device transports plus the named differences | passed |
| REQ-SHL-SELF-STEAL-PORT | ANS-1794807559120996 | `test_split_hop_live_node_a_keeps_the_production_device_transports` requires `reality_self_steal_port: 8444` and that it equals none of the default Xray and nginx-xhttp ports; the role's own port guard is covered by `test_reality_self_steal.py` | passed |
| REQ-SHL-SELF-STEAL-IDENTITY | ANS-1794807590109058 | Live deploy of Node A at 441c02b4 with `make verify`, `source-drift` and `security-verify`; outside scan with one certificate on TCP/443, TCP/8443 and QUIC/443; `scripts/sshd-promotion-proof.py` status passed from the sentinel on Node B | passed |
