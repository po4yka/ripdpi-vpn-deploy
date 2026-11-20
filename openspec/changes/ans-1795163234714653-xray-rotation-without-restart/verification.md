---
task_id: ANS-1795163234714653
change: ans-1795163234714653-xray-rotation-without-restart
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: required
dry_run_evidence: null
staging: not_applicable
staging_evidence: The staging profile renders the same three templates; the native CI lanes run real logrotate against a real Xray.
live: required
live_evidence: null
client: not_applicable
client_evidence: No client payload, credential or share link changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-AUDIT-GENERATION | ANS-1795163509998271 | `tests/unit/test_monitoring_logrotate.py::test_xray_rotation_never_restarts_or_signals_the_service` | pending |
| REQ-DRR-ROTATE | ANS-1795163509998271 | same unit test on every profile; native `test_transport_logrotate_native.py` and `tests/native/transport_acceptance/test_rotation.py` in CI | pending |
| REQ-P1-XRAY | ANS-1795163509998271 | native rotation lanes compare `MainPID` and require the rotated copy and continued traffic | pending |
| REQ-DRR-XRAY-RUNTIME | ANS-1795163550770687 | `tests/unit/test_transport_service_sandbox.py::test_xray_unit_hides_host_state_and_stays_below_the_host_file_table`, `make snapshot-check` | pending |
