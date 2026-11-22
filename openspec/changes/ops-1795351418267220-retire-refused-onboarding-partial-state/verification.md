---
task_id: OPS-1795351418267220
change: ops-1795351418267220-retire-refused-onboarding-partial-state
commit_sha: null
local: passed
local_evidence: "make -k -j 4 check under mise on the implementation tree: every target passed except task-check (stale generated board; passed after ./taskctl generate-board) and test-unit (12774 passed, 19 failed in untouched modules such as test_deploy_controller, test_observability_deadman and test_operator_automation; all 19 passed when rerun alone, so they are load-induced). test_retire_unbound_staging_client, test_disposable_liveness_executor and test_disposable_promotion: 245 passed. The new refused-onboarding tests fail against the previous script, and the assignment case fails without the profile-record check. openspec validate --strict passed. A read-only run of the identity check against the 2026-11-22 archived outputs with their retained intent accepted all three. One independent review: no blocking defects; the assignment-record window, non-string scope, uncategorized RecursionError and resume-category wording were fixed."
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: The retirement verbs are local recovery commands; no deploy check mode exercises them.
staging: not_applicable
staging_evidence: The 2026-11-22 run was already cleaned up by hand. The exact identity check was run read-only against that run's archived authority, liveness config and executor manifest copy with its retained intent and accepted all three; reproducing on staging needs a deliberately refused onboarding.
live: not_applicable
live_evidence: No provider, host or runtime behavior changes; the verbs never contact providers or hosts.
client: not_applicable
client_evidence: Client payloads are unchanged; retirement removes the same encrypted entries as before.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-REGISTRY-REFUSED-ONBOARDING | OPS-1795351768504438 | test_retire_unbound_staging_client::test_refused_onboarding_partial_state_retires_client_and_executor, test_refused_onboarding_partial_state_change_refuses_resume | passed |
| REQ-REGISTRY-PARTIAL-FOREIGN | OPS-1795351826854045 | test_retire_unbound_staging_client::test_refused_onboarding_partial_state_refuses_foreign_shapes, test_retirement_refuses_any_onboarding_output | passed |
