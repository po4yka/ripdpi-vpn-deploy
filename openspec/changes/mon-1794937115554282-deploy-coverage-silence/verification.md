---
task_id: MON-1794937115554282
change: mon-1794937115554282-deploy-coverage-silence
commit_sha: a6b0e23e8a95bcb8a43591072a2a411891e87ef3
local: passed
local_evidence: "make -k -j 4 check on the pre-review tree: every target passed except test-unit (12190 passed, 10 failed). Two failures were test_deployment_silence cases edited during the run; the other eight were timeouts or a connection reset under parallel load. After the review fixes the eight tests, test_deployment_silence, test_device_lifecycle_io, test_observability_operator, test_deploy_controller and test_check_certs_key_match ran serially: 397 passed, 1 failed (test_transport_site_transaction::test_protected_failure_restores_ingress_before_frontend_resume[xray]); that test passed 3/3 alone and touches no changed module, so it is timing-sensitive. make docs-check, taskctl validate and openspec validate --strict passed. One independent review: one high finding (failed rotation treated as success) and one medium (unmonitored node) fixed with regression tests; collector-node scope and environment admission documented as accepted."
remote_ci: required
remote_ci_evidence: "PR 634 checks passed before merge (592fe8da). Main CI on 592fe8da failed in native runtime integration on a policy-ratelimit template regression from 9933b01a that this change does not touch; PR 638 fixed it, and main CI run 44362966134 on 42a5ab8b passed on attempt 2 (attempt 1 failed in four-transport acceptance core-2 on a Go module download timeout in the AmneziaWG checksum test)."
dry_run: required
dry_run_evidence: "make dry-run ANSIBLE_LIMIT=node-c ANSIBLE_TAGS= at 42a5ab8b with the silence configured (owner primary-operator, collector node-b, environment fleet, monitoring inventory, Tailnet pins): ok=668 changed=2 failed=0 (node manifest identity and the pending transport-egress candidate). The gateway audit on node-b has no silence event between 2026-11-18T15:26:29Z and the deploy at 2026-11-19T02:34:54Z, so the dry-run created no silence."
staging: not_applicable
staging_evidence: The observability collector and silence gateway exist only on the fleet; staging has no gateway to receive the silence.
live: required
live_evidence: "Owner-approved make deploy on node-c (vultr-p2-vultr) at 42a5ab8b, 2026-11-19T02:34:20Z-03:02:44Z: deploy, verify, source-drift, security-verify, smoke-test and protocol-liveness exit 0; no maintenance silence warning. Gateway audit on node-b: main silence created 02:34:54Z (scope component=observability-external-coverage, environment=fleet, node=vultr-p2-vultr; reason deploy-transport-restart), tail created 02:57:52Z, main deleted 02:57:55Z, tail expired 03:02:50Z; no active silence afterwards. ObservabilityExternalCoverageUnavailable for vultr-p2-vultr was pending 02:45:30Z and firing 02:46:30Z-02:51:00Z, wholly inside the main silence, so Alertmanager held it under the silence, and it did not fire after the tail expired. ObservabilitySourceIdentityMismatch fired 03:03Z-03:17Z between the core deploy and the agent rotation, which is outside this coverage-only scope; all alerts except the pipeline canary were clear from 03:17:25Z through 03:27:57Z."
client: not_applicable
client_evidence: No client payload or device artifact changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OPS-DEPLOY-SILENCE-SCOPE | MON-1794937405270339 | test_deploy_controller::test_only_deploy_mode_wraps_site_in_the_node_coverage_silence, test_device_lifecycle_io::test_runtime_silences_node_coverage_only_around_rotation, test_deployment_silence::test_success_tails_before_deleting_the_exact_coverage_silence | Passed locally and live |
| REQ-OPS-DEPLOY-SILENCE-LIFECYCLE | MON-1794937362082306 | test_deployment_silence::test_success_tails_before_deleting_the_exact_coverage_silence, test_failed_mutation_deletes_without_tail_and_keeps_its_error | Passed locally and live |
| REQ-OPS-DEPLOY-SILENCE-FAILURE | MON-1794937405270339 | test_deployment_silence::test_gateway_failure_only_warns_categorically, test_device_lifecycle_io::test_runtime_silences_node_coverage_only_around_rotation[failed status] | Passed locally |
| REQ-OPS-DEPLOY-SILENCE-AUTHORITY | MON-1794937362082306 | test_deployment_silence::test_unconfigured_or_unidentified_node_makes_no_gateway_call, test_operator_admits_collector_by_its_own_environment_without_source_binding, test_operator_refuses_ambiguous_unsafe_or_unmonitored_silence_calls | Passed locally |
