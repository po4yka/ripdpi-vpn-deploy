---
task_id: ANS-1794584539221043
change: ans-1794584539221043-liveness-sentinel-role
commit_sha: null
local: passed
local_evidence: "make molecule-test ROLE=liveness-sentinel passed (converge, idempotence changed=0, verify with two refusal cases) on an amd64 container through the default Colima profile, because container DNS fails in the vpn-tests-amd64 profile; ansible-lint on the role and site.yml passed; tests/unit/test_liveness_sentinel_role.py, test_provision_disposable_liveness_runtime.py, test_tailnet_management.py, test_deploy_profile_guard.py and test_governance_counts.py passed; check-deploy-profile.py passed; make docs-check passed. The AWG build path was not executed: it needs controller-side source bundles."
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: Pending a dry-run of the live Node B with the role, separately authorized.
staging: not_applicable
staging_evidence: The role installs inert artifacts and is exercised by Molecule; the live Node B is a research node.
live: required
live_evidence: Pending the authorized converge of the live Node B and fetch of expected-runtime.json.
client: not_applicable
client_evidence: No client traffic; the sentinel is measurement-only.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-LSR-INSTALL | ANS-1794584586331605 | `make molecule-test ROLE=liveness-sentinel`: layout, root-owned 0755 binaries, planted `/usr/local/bin/xray` link untouched, wrong digest and wrong staged version both refused with the previous binary and empty staging | Passed |
| REQ-LSR-PINS | ANS-1794584586331605 | `tests/unit/test_liveness_sentinel_role.py::test_disposable_flow_and_role_read_the_same_pin_file_and_no_digest_is_duplicated`; `tests/unit/test_provision_disposable_liveness_runtime.py` | Passed |
| REQ-LSR-PROBE | ANS-1794584586331605 | `tests/unit/test_liveness_sentinel_role.py::test_probe_prefers_the_role_prefix_and_falls_back_to_path` | Passed |
| REQ-LSR-OUTPUT | ANS-1794584586331605 | Molecule verify asserts `expected-runtime.json` equals the installed sing_box and xray versions | Passed |
| REQ-LSR-AWG | ANS-1794584586331605 | ansible-lint and syntax-check of `tasks/awg.yml`; the installer's own unit tests. The role's AWG build was not executed offline | Not executed |
| REQ-LSR-GATING | ANS-1794584586331605 | `scripts/check-deploy-profile.py`; `tests/unit/test_tailnet_management.py::test_split_hop_live_node_b_matches_the_listener_free_staging_node_b`; `test_role_prefix_matches_the_probe_and_the_live_node_b_is_the_only_enabled_host_profile` | Passed |
