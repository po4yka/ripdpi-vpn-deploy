---
task_id: SCR-1795082568279731
change: scr-1795082568279731-deploy-slow-channel-tolerance
commit_sha: null
local: required
local_evidence: 'make -k check -j 4 at 5ff7f3c7 plus this change: every target passed except test-unit; test-unit reruns after the fixes: tests/unit/test_deploy_controller.py 183 passed, test_bootstrap_tailnet.py 148 passed, full make test-unit 12232 passed with one load-sensitive failure (test_observability_deadman_receiver worker-capacity test, passes alone, untouched by this change); make task-check and make docs-check passed'
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: Dry-run is deliberately not gated and gains only the session options, which the unit tests cover; no node state changes.
staging: not_applicable
staging_evidence: The change is controller-local SSH behaviour with no node-side or role change; staging adds no evidence beyond the unit tests.
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
| REQ-OPS-CHANNEL-SESSION | SCR-1795082805831806 | test_frozen_transport_is_portable_and_retains_original_host_key_identity (real ssh -G), test_installer_real_ansible_preserves_local_delegation | Passed locally |
| REQ-OPS-CHANNEL-PROMPT | SCR-1795082805831806 | test_frozen_transport_is_portable_and_retains_original_host_key_identity | Passed locally |
| REQ-OPS-CHANNEL-GATE | SCR-1795082820949890 | test_deploy_measures_tailnet_route_before_mutation, test_route_gate_skips_dry_run_and_public_transport, test_route_gate_parses_cli_replies | Passed locally |
| REQ-OPS-CHANNEL-REFUSAL | SCR-1795082820949890 | test_deploy_measures_tailnet_route_before_mutation, test_route_gate_parses_cli_replies | Passed locally |
