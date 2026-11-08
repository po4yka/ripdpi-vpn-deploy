---
task_id: SCR-1794116837161459
change: scr-1794116837161459-device-private-delivery
commit_sha: null
local: passed
local_evidence: On task/device-private-delivery over origin/main 79c3a7fe, pytest over tests/unit/test_device_lifecycle*.py and test_device_migration*.py gave 294 passed and 16 errors; all 16 errors are the Linux-only tests in test_device_lifecycle_probe_native.py, which assert sys.platform == 'linux' on macOS. make docs-check passed. mise exec -- make -k -j 4 check failed only in test-unit with 50 failures in test_sshd_ownership, test_sshd_migrate, test_evidence_ssh_admission, test_watchdog_templates and test_workspace_status (11598 passed); a clean origin/main worktree on the same machine fails the same 50, and no device lifecycle or migration test failed. task-check, validate and the other gate checks passed.
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: The change is controller code; its live use is the separately authorized issuance of personal-pixel-incy.
staging: not_applicable
staging_evidence: No runtime role, template or host behavior changes.
live: required
live_evidence: null
client: not_applicable
client_evidence: Client acceptance of the issued device belongs to SCR-1794075997223882.
artifact: required
artifact_evidence: docs/how-to/device-lifecycle.md documents private delivery. PR review pending.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DEVICE-PRIVATE-DELIVERY | SCR-1794117494014479 | test_publisher_less_ripdpi_issue_and_refresh_deliver_only_a_private_artifact (issue, refresh, revoke with publishers: []), test_publisher_less_manifest_is_private_and_refuses_expiry[issue,refresh]; existing publisher and native tests unchanged and passing | passed |
| REQ-DEVICE-PRIVATE-EXPIRY | SCR-1794118002578495 | test_publisher_less_manifest_is_private_and_refuses_expiry matches private-delivery-does-not-enforce-expiry | passed |
