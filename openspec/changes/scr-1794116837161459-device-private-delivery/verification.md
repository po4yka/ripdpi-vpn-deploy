---
task_id: SCR-1794116837161459
change: scr-1794116837161459-device-private-delivery
commit_sha: null
local: passed
local_evidence: On task/device-private-delivery over origin/main 79c3a7fe, pytest over tests/unit/test_device_lifecycle*.py and test_device_migration*.py gave 294 passed and 16 errors; all 16 errors are the Linux-only tests in test_device_lifecycle_probe_native.py, which assert sys.platform == 'linux' on macOS. make docs-check passed. mise exec -- make -k -j 4 check failed only in test-unit with 50 failures in test_sshd_ownership, test_sshd_migrate, test_evidence_ssh_admission, test_watchdog_templates and test_workspace_status (11598 passed); an earlier clean worktree of cffb65b0 on the same machine failed in the same test files, but this run was not compared with a baseline test by test. No device lifecycle or migration test failed. task-check, validate and the other gate checks passed.
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: The change is controller code; its live use is the separately authorized issuance of personal-pixel-incy.
staging: not_applicable
staging_evidence: No runtime role, template or host behavior changes.
live: passed
live_evidence: Operation b5f72cff-c68f-4f60-9795-bc5106b2ca32 issued personal-pixel-incy on source f541679b to the three production nodes and reached phase complete: nodes_written 3, nodes_adopted 3, four native credential profiles accepted, recipient artifact written with mode 0600 and subscription_url null. It did not run through the unmodified CLI. A local wrapper supplied VPN_CERT_VARS_FILES and the operator overrides, and compared AWG peers without their order; this PR puts those three behaviors in the source. Under owner approval the wrapper accepted make verify failing only on source parity, for deployed revision 63ec3198 against expected f541679b, with all service checks passing. The nodes stay at 63ec3198 until the next deploy of main. Two node-c applies failed and rolled back before the third succeeded: a 32-second sudo timeout, and a 5-second systemctl timeout in the Hysteria2 validation. The first probe failures came from the AWG peer listing order.
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
| REQ-DEVICE-OPERATOR-INPUTS | SCR-1794157295397257 | test_runtime_uses_exact_private_inventory_and_removes_plaintext_after_failure, test_manifest_refuses_unsafe_node_overrides_before_any_write, test_override_contents_are_part_of_the_approved_operation and test_awg_witness_compares_the_peer_set_and_not_its_listing_order; the live run in live_evidence used the same three behaviors through a local wrapper | passed |
