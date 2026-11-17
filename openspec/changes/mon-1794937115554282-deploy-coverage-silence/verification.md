---
task_id: MON-1794937115554282
change: mon-1794937115554282-deploy-coverage-silence
commit_sha: a6b0e23e8a95bcb8a43591072a2a411891e87ef3
local: passed
local_evidence: "make -k -j 4 check on the pre-review tree: every target passed except test-unit (12190 passed, 10 failed). Two failures were test_deployment_silence cases edited during the run; the other eight were timeouts or a connection reset under parallel load. After the review fixes the eight tests, test_deployment_silence, test_device_lifecycle_io, test_observability_operator, test_deploy_controller and test_check_certs_key_match ran serially: 397 passed, 1 failed (test_transport_site_transaction::test_protected_failure_restores_ingress_before_frontend_resume[xray]); that test passed 3/3 alone and touches no changed module, so it is timing-sensitive. make docs-check, taskctl validate and openspec validate --strict passed. One independent review: one high finding (failed rotation treated as success) and one medium (unmonitored node) fixed with regression tests; collector-node scope and environment admission documented as accepted."
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: The observability collector and silence gateway exist only on the fleet; staging has no gateway to receive the silence.
live: required
live_evidence: null
client: not_applicable
client_evidence: No client payload or device artifact changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OPS-DEPLOY-SILENCE-SCOPE | MON-1794937405270339 | test_deploy_controller::test_only_deploy_mode_wraps_site_in_the_node_coverage_silence, test_device_lifecycle_io::test_runtime_silences_node_coverage_only_around_rotation, test_deployment_silence::test_success_tails_before_deleting_the_exact_coverage_silence | Passed locally; live pending |
| REQ-OPS-DEPLOY-SILENCE-LIFECYCLE | MON-1794937362082306 | test_deployment_silence::test_success_tails_before_deleting_the_exact_coverage_silence, test_failed_mutation_deletes_without_tail_and_keeps_its_error | Passed locally; live pending |
| REQ-OPS-DEPLOY-SILENCE-FAILURE | MON-1794937405270339 | test_deployment_silence::test_gateway_failure_only_warns_categorically, test_device_lifecycle_io::test_runtime_silences_node_coverage_only_around_rotation[failed status] | Passed locally |
| REQ-OPS-DEPLOY-SILENCE-AUTHORITY | MON-1794937362082306 | test_deployment_silence::test_unconfigured_or_unidentified_node_makes_no_gateway_call, test_operator_admits_collector_by_its_own_environment_without_source_binding, test_operator_refuses_ambiguous_unsafe_or_unmonitored_silence_calls | Passed locally |
