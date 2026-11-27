---
task_id: SCR-1795774108061951
change: scr-1795774108061951-management-route-warmup
commit_sha: null
local: passed
local_evidence: 'python3 -m pytest tests/unit/test_deploy_controller.py tests/unit/test_bootstrap_tailnet.py: 350 passed in a parallel run; the 16 tests that hit the 25 s invoke timeout under a load average of about 840 passed when rerun serially (16 passed). make docs-check: 12 passed. taskctl openspec cli validate --strict passed for this change and for scr-1795082568279731-deploy-slow-channel-tolerance.'
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: The change touches only the operator-side deploy controller; no staging node behaviour changes.
live: required
live_evidence: null
client: not_applicable
client_evidence: No client contract or payload changes.
artifact: not_applicable
artifact_evidence: No build or release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-OPS-ROUTE-WARMUP | SCR-1795774279138177 | test_both_modes_warm_and_measure_tailnet_route_before_ssh (warm-up before the first SSH command; `unreachable` cases), test_route_gate_parses_cli_replies (`mapped-probed`) | Passed locally |
| REQ-OPS-ROUTE-SCOPE | SCR-1795774279138177 | test_route_gate_skips_public_transport (dry-run and deploy), test_route_gate_parses_cli_replies (CI handoff, public and host-name transports) | Passed locally |
| REQ-OPS-ROUTE-BOTH-MODES | SCR-1795774279138177 | test_both_modes_warm_and_measure_tailnet_route_before_ssh (dry-run and deploy for relayed, direct, lossy and slow routes); live preview route report pending | Passed locally |
| REQ-OPS-ROUTE-SILENCE | SCR-1795774324586353 | test_frozen_transport_is_portable_and_retains_original_host_key_identity (real `ssh -G`), test_installer_real_ansible_preserves_local_delegation | Passed locally |
