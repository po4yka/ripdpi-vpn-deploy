---
task_id: ANS-1794322927427537
change: ans-1794322927427537-split-hop-staging-cohort-profiles
commit_sha: null
local: passed
local_evidence: "On base f1961272: check-deploy-profile.py, the no-listener promotion test (8 cases including the shipped profile), the Node A profile and Tailnet profile tests, make snapshot-check (187 templates) and make docs-check passed. make -k -j 4 check passed every gate except test-unit, whose 50 failures are the same set on clean main f1961272 when rerun serially (Linux-only native and macOS SSH-environment tests)."
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: Pending a staging dry-run of Node B with vpn-split-hop-egress-staging and of Node A with vpn-split-hop-ingress-staging, recorded under ANS-1794231660855533.
staging: required
staging_evidence: Pending the ANS-1794231660855533 staging pair converging through these cohorts.
live: not_applicable
live_evidence: The profiles are scoped to disposable staging; a production split-hop cohort is separate work.
client: not_applicable
client_evidence: Client traffic through the staged pair is evidence for ANS-1794231660855533.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SHS-EGRESS | ANS-1794323562304527 | `tests/unit/test_deploy_controller.py::test_no_listener_promotion_needs_an_explicit_egress_only_listener_free_host[shipped-staging-profile]` | Passed |
| REQ-SHS-INGRESS | ANS-1794323562304527 | `tests/unit/test_tailnet_management.py::test_split_hop_node_a_profiles_keep_the_staging_transports` | Passed |
| REQ-SHS-ADMISSION | ANS-1794323562304527 | `python3 scripts/check-deploy-profile.py` | Passed |
| REQ-SHS-ADMISSION | ANS-1794324110536208 | `make docs-check` on the corrected pilot guide and profile reference | Passed |
