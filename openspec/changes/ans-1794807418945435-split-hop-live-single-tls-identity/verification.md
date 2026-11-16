---
task_id: ANS-1794807418945435
change: ans-1794807418945435-split-hop-live-single-tls-identity
commit_sha: null
local: passed
local_evidence: "On the working tree of the change, based on 11b50083: pytest for test_tls_identity_preflight.py, test_deploy_profile_guard.py, test_reality_self_steal.py and the profile tests test_split_hop_live_node_a_keeps_the_production_device_transports, test_committed_profiles_carry_only_the_neutral_placeholder_origin and test_disposable_staging_profiles_serve_the_generated_masquerade_origin: 64 passed, exit 0. scripts/check-deploy-profile.py exit 0. Not run: make check, Molecule and the snapshot suite (no template or role changed)."
remote_ci: required
remote_ci_evidence: Pending the hosted CI run for the pull request and for the merge commit.
dry_run: required
dry_run_evidence: "Pending a full dry-run of the live Node A from the merged revision. Before this change, on 2026-11-16, the dry-run at 00daf904 refused the node at the transport input preflight (AmneziaWG default port and published value set), and the TLS identity preflight would have refused it next."
staging: not_applicable
staging_evidence: The staging profiles do not change, and the changed profile is used only by the live pair.
live: required
live_evidence: Pending the deploy of the live Node A with make verify and make security-verify, and a fresh liveness proof from the sentinel on Node B.
client: required
client_evidence: Pending the device refresh and one handshake for each transport from the device.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SHL-SELF-STEAL-IDENTITY | ANS-1794807559120996 | `test_committed_profiles_that_need_a_layout_change_or_an_exception_on_production` runs the real preflight task for every committed profile: the live family-egress profile now passes and the other three split-hop Node A profiles still refuse; `test_split_hop_live_node_a_keeps_the_production_device_transports` pins the profile to the device transports plus the named differences | passed |
| REQ-SHL-SELF-STEAL-PORT | ANS-1794807559120996 | `test_split_hop_live_node_a_keeps_the_production_device_transports` requires `reality_self_steal_port: 8444` and that it equals none of the default Xray and nginx-xhttp ports; the role's own port guard is covered by `test_reality_self_steal.py` | passed |
| REQ-SHL-SELF-STEAL-IDENTITY | ANS-1794807590109058 | Live rollout of Node A | pending |
