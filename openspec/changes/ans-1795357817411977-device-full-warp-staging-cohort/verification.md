---
task_id: ANS-1795357817411977
change: ans-1795357817411977-device-full-warp-staging-cohort
commit_sha: null
local: passed
local_evidence: "2026-11-22 on cf39b40bb plus this change: profile tests (test_deploy_profile_guard, test_ci_real_deploy, test_public_site_contract, test_tailnet_management, test_listener_contract) 410 passed; every other unit test that reads group_vars, excluding native_runtime, 1320 passed after test_tls_identity_preflight gained the new cohort in its expected production-refusal set (the cohort has the device-full-staging layout); scripts/check-deploy-profile.py passed; make docs-check and make task-check passed."
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: A new staging-only cohort; no production node uses it.
staging: required
staging_evidence: null
live: not_applicable
live_evidence: Staging-only cohort; production profiles are unchanged.
client: not_applicable
client_evidence: No client contract changes.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-WARP-STAGING-COHORT | ANS-1795358025489176 | `test_live_explicit_profile_surfaces_are_locked` compares the two maps and the staging origin | pass (local) |
| REQ-WARP-STAGING-FAMILY | ANS-1795358025489176 | `scripts/check-deploy-profile.py` passed with the cohort in `family_profiles`; `test_live_family_profile_list_includes_explicit_profiles` | pass (local) |
