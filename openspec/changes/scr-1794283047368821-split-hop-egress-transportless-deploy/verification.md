---
task_id: SCR-1794283047368821
change: scr-1794283047368821-split-hop-egress-transportless-deploy
commit_sha: null
local: passed
local_evidence: "test_deploy_controller, test_sshd_baseline_controller and test_check_certs_key_match passed (272); the other suites that copy deploy-controller passed (282). terraform test in the UpCloud root passed (24 runs). make docs-check passed. make -k -j 4 check: task-check, validate and ci-fast passed except 50 unit failures (sshd_ownership, sshd_migrate, evidence_ssh_admission, watchdog_templates, workspace_status) that fail identically on clean main. Removing each guard (proof skip, target binding, listener contract, admission, shadowing sources, default-on transports, egress role, both firewall preconditions) failed a test."
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: Pending the Node B dry-run of the split-hop staging pair under ANS-1794231660855533.
staging: required
staging_evidence: Pending a staging Node B converged by make deploy with a no-public-listener promotion.
live: required
live_evidence: Pending the live Node B deployment under ANS-1794231660855533.
client: not_applicable
client_evidence: Node B serves no client; client evidence belongs to ANS-1794231660855533.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-NLP-CONTRACT | SCR-1794283738183240 | `tests/unit/test_deploy_controller.py::test_no_listener_promotion_needs_an_explicit_egress_only_listener_free_host` (admitted, listener-published, contract-absent, contract-group-wide, contract-in-secrets) | Passed locally |
| REQ-NLP-TOGGLES | SCR-1794283738183240 | Same test (hysteria-default-on, egress-role-off) | Passed locally |
| REQ-NLP-TRANSACTION | SCR-1794284337233359 | `tests/unit/test_sshd_baseline_controller.py::test_no_listener_promotion_keeps_fresh_ssh_checks_and_runs_no_sentinel_proof`, `::test_no_listener_promotion_bound_to_another_target_refuses_before_prepare` | Passed locally |
| REQ-NLP-PROVIDER | SCR-1794284920176736 | `terraform/providers/upcloud/tests/server.tftest.hcl` runs `split_hop_egress_node_has_no_public_protocol_listener`, `split_hop_egress_node_rejects_public_protocols` | Passed locally |
