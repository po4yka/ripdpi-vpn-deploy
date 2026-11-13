---
task_id: ANS-1794574965811688
change: ans-1794574965811688-split-hop-live-cohort-profiles
commit_sha: null
local: passed
local_evidence: "check-deploy-profile.py passed with the three live cohorts outside family_profiles; tests/unit/test_tailnet_management.py passed (145), including the live Node A and Node B contract tests, which fail when a live Node A disables backup; make docs-check passed."
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: Pending a dry-run of each live node with its cohort, recorded under ANS-1794231660855533.
staging: not_applicable
staging_evidence: The topology passed staging with the staging cohorts under ANS-1794231660855533; these cohorts differ only in the device profile base and recovery services.
live: required
live_evidence: Pending the authorized live research pair converging through these cohorts.
client: required
client_evidence: Pending authenticated device traffic through the live Node A, recorded under ANS-1794231660855533.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SHL-EGRESS | ANS-1794576187734721 | `tests/unit/test_tailnet_management.py::test_split_hop_live_node_b_matches_the_listener_free_staging_node_b` | Passed |
| REQ-SHL-INGRESS | ANS-1794576187734721 | `tests/unit/test_tailnet_management.py::test_split_hop_live_node_a_keeps_the_production_device_transports` (fails when a live Node A disables backup) | Passed |
| REQ-SHL-ADMISSION | ANS-1794576187734721 | `python3 scripts/check-deploy-profile.py`; `test_live_fleet_profiles_enable_only_reviewed_tailnet_management_sources` | Passed |
