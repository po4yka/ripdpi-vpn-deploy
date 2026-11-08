---
task_id: MON-1794126016474351
change: mon-1794126016474351-telegram-alert-messages
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: required
staging_evidence: null
live: required
live_evidence: null
client: not_applicable
client_evidence: The change affects operator notifications and no VPN client path.
artifact: required
artifact_evidence: null
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-ALERT-MESSAGE | MON-1794126893076662 | tests/unit/test_observability_telegram_delivery.py | passed locally |
| REQ-ALERT-ACTION | MON-1794126893076662 | tests/unit/test_observability_control_plane_alerting.py, promtool rule cases | passed locally |
| REQ-ALERT-OLDER-RULES | MON-1794126893076662 | test_relay_delivers_alerts_from_older_rules_without_an_action | passed locally |
| REQ-KUMA-MESSAGE | MON-1794127442259762 | Documented template rendered with liquidjs 10.26.0 for down, up and test contexts | passed locally; Kuma UI not applied |

## Local run

The status of `local` stays `required` because the local workstation cannot complete the gate. CI must supply the missing results.

- `make -j 4 -k check` on base revision 1179aeb6 with the staged change: 11607 tests passed and 50 tests failed. All other checks of the gate passed.
- 49 of the 50 failures are in `test_evidence_ssh_admission.py`, `test_sshd_migrate.py`, `test_sshd_ownership.py` and `test_watchdog_templates.py`. The same 49 tests fail on a clean checkout of 1179aeb6, so this change does not cause them.
- The 50th failure is `test_workspace_status.py::test_task_pointers_use_real_taskctl`. It also fails when it runs alone, because one `taskctl show` call took 516 seconds on this workstation and `workspace-status` allows 300 seconds.
- `make molecule-test ROLE=observability_control_plane` did not run. The pinned Molecule image has no linux/arm64 manifest for the local Docker host. The role scenario has no fixture that uses annotations or message text.
- The native Alertmanager test (`native_runtime` marker) did not run because `ALERTMANAGER_BIN` is not set.
- Real Telegram delivery and the Kuma UI change need separate authorization and did not occur.
