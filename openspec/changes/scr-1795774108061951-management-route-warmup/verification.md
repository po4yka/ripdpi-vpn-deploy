---
task_id: SCR-1795774108061951
change: scr-1795774108061951-management-route-warmup
commit_sha: f5ca1809a6093253aaa944f0c8782e82dbe16441
local: passed
local_evidence: 'python3 -m pytest tests/unit/test_deploy_controller.py tests/unit/test_bootstrap_tailnet.py: 350 passed in a parallel run; the 16 tests that hit the 25 s invoke timeout under a load average of about 840 passed when rerun serially (16 passed). make docs-check: 12 passed. taskctl openspec cli validate --strict passed for this change and for scr-1795082568279731-deploy-slow-channel-tolerance.'
remote_ci: passed
remote_ci_evidence: 'PR po4yka/ripdpi-vpn-deploy#779 merged as f5ca1809a. ci run 46027663778 on main at f5ca1809a: pytest unit tests and all four pytest groups succeeded; the run failed only in contract-sync (client vendored copy matches SoT) and the required-checks aggregate, the same failure as run 46004309890 on the preceding main commit 813683fca, from a contract change outside this task.'
dry_run: passed
dry_run_evidence: 'Timed check-mode preview of node-a (make dry-run, full graph) from a clean worktree at f5ca1809a, started 2026-11-27T16:07:56Z: the controller warmed and measured the route before readiness and reported "management route relayed, median 166 ms"; dry-run 1115.7 s, recap ok=706 changed=3 unreachable=0 failed=0; decrypted secrets absent afterwards. Receipt and age-encrypted log in the local operator kit (preview-timing-20261126/warm-node-a).'
staging: not_applicable
staging_evidence: The change touches only the operator-side deploy controller; no staging node behaviour changes.
live: passed
live_evidence: 'The same node-a preview ran against the production node over the relayed Tailnet management route (no direct path) and completed without a lost session; it changed nothing on the node (check mode).'
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
| REQ-OPS-ROUTE-BOTH-MODES | SCR-1795774279138177 | test_both_modes_warm_and_measure_tailnet_route_before_ssh (dry-run and deploy for relayed, direct, lossy and slow routes); node-a preview at f5ca1809a reported "management route relayed, median 166 ms" | Passed |
| REQ-OPS-ROUTE-SILENCE | SCR-1795774324586353 | test_frozen_transport_is_portable_and_retains_original_host_key_identity (real `ssh -G`), test_installer_real_ansible_preserves_local_delegation | Passed locally |
