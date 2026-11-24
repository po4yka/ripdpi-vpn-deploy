---
task_id: TFR-1795357890236562
change: tfr-1795357890236562-remote-state-readers-w3b
commit_sha: f9d6a5139500016f895d25e4eececafb298df40a
local: passed
local_evidence: "make -k check -j 4 at 21a924740: test-unit 12823 passed and every other target passed except terraform-init, which could not reach registry.opentofu.org (network timeout; no Terraform root changed, and it passed in the earlier gate run at 20c3f8e13)"
remote_ci: passed
remote_ci_evidence: "po4yka/ripdpi-vpn-deploy ci run 45410025050 on main at f9d6a5139: completed with success, every job passed. That revision holds the state readers and the stable pulled-state bytes fix found during the first rollout prepare."
dry_run: not_applicable
dry_run_evidence: No Ansible input changes.
staging: not_applicable
staging_evidence: No live action in this change; the next authorized staging cleanup exercises the pulled state.
live: not_applicable
live_evidence: Scripts only; no infrastructure change.
client: not_applicable
client_evidence: No client-visible change.
artifact: not_applicable
artifact_evidence: No release artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-STATE-READ-PULL | TFR-1795358620771976 | Every reader pulls through `tofu_state.pull` or the tailnet trusted binary; old `--state`, `STAGING_CLEANUP_STATE`, `provider_state_path` and path-bound manifests refused (`test_tofu_state.py`, guard old-shape tests, `test_terraform_snapshot_has_no_local_state_and_refuses_old_manifest`) | passed |
| REQ-STATE-READ-FAILCLOSED | TFR-1795358620771976 | `test_pull_refuses_failure_and_oversized_state`, `test_pull_kills_a_wrapper_that_exceeds_the_timeout`, `test_runtime_reads_state_through_the_backend_and_never_treats_failure_as_empty`, `test_unreadable_state_is_not_reported_as_unprovisioned`, guard and retirement pull-failure cases | passed |
| REQ-STATE-READ-BINDING | TFR-1795358675141561 | Cleanup manifests bind `{sha256}` of pulled bytes and re-pull at each step (`test_staging_cleanup_guard.py`, `test_vultr_staging_cleanup_guard.py`, `test_state_that_differs_or_cannot_be_pulled_refuses_load`); tailnet target drift refused before plan | passed |
| REQ-STATE-READ-CI | TFR-1795358658062021 | `test_orchestration_requires_deploy_and_verified_cleanup` checks the override, backend file and passphrase reach init and every pull, survive resume, and are removed once no teardown is owed | passed |
