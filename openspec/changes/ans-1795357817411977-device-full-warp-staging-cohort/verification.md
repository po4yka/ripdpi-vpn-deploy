---
task_id: ANS-1795357817411977
change: ans-1795357817411977-device-full-warp-staging-cohort
commit_sha: null
local: passed
local_evidence: "2026-11-22 on cf39b40bb plus this change: profile tests (test_deploy_profile_guard, test_ci_real_deploy, test_public_site_contract, test_tailnet_management, test_listener_contract) 410 passed; every other unit test that reads group_vars, excluding native_runtime, 1320 passed after test_tls_identity_preflight gained the new cohort in its expected production-refusal set (the cohort has the device-full-staging layout); scripts/check-deploy-profile.py passed; make docs-check and make task-check passed. 2026-11-23 on 2416ea5a7 plus the onboarding step: test_disposable_promotion, test_prepare_disposable_promotion_intent and test_retire_unbound_staging_client 248 passed, including the real Make publication with PROMOTION_COHORT."
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: A new staging-only cohort; no production node uses it.
staging: required
staging_evidence: "Partial, 2026-11-23/24: one disposable UpCloud node vpn-ci-staging-acc4 (Debian 13, this cohort) was provisioned, Tailnet-enrolled and ownership-migrated; its dry-runs passed. Successive deploys found nine first-install defects in the WARP path and its Debian 13 prerequisites, fixed in PRs 694, 701, 704, 705, 710, 711, 712, 713 and 714. After the namespace-handle and terms-of-service fixes, a WARP registration was created once on the node inside the role-owned namespace, and the node was returned to its accepted state (vendor masked, no namespace). The operator executor's six-hour window ran out before a deploy at the final revision, so no deploy completed. Not done: a successful deploy of this cohort, the WARP namespace refresh, the reboot check and the four-profile proof. The node was destroyed through make staging-destroy with verified provider absence; its client and executor were retired, and its Tailnet device and key were deleted."
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
| REQ-WARP-STAGING-ONBOARDING | ANS-1795444222175506 | `test_publishes_valid_private_intent_and_exact_alias_mapping_without_key_reads[device-full-warp-staging]`, `test_refusal_preserves_inputs_and_existing_destination[missing-cohort]` and `[foreign-cohort]`, the real Make publication test | pass (local) |
| REQ-WARP-STAGING-FAMILY | ANS-1795358025489176 | `scripts/check-deploy-profile.py` passed with the cohort in `family_profiles`; `test_live_family_profile_list_includes_explicit_profiles` | pass (local) |
