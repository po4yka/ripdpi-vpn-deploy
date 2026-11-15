---
task_id: SEC-1794728606515594
change: sec-1794728606515594-node-address-disclosure
commit_sha: 839b45f8
local: passed
local_evidence: "make -k -j 4 check exit 0 on the tree before the commit, where the new files were still untracked, so the tracked-address guard did not scan them; it later flagged reverse-DNS literals in test_doh_lookup.py, fixed in d92e9fd3 (12051 unit tests passed, 551 vpnd tests passed, ansible-lint, shellcheck, snapshot-check, docs-check, task-check); focused modules for the changed scripts and the watchdog role passed. Molecule for the watchdog role did not run: the pinned Debian image has no arm64 manifest on the operator workstation. One independent review; its findings were fixed before the gate run. Integrated gate on be0d5908 (all six tasks on one branch): make -k -j 4 check passed every target except test-unit, where 12170 cases passed and one failed, test_tailnet_network_executor.py::test_expiry_serializes_with_forward_mark_and_rolls_back_true; it is timing-sensitive under the parallel run, passes alone and with its file, and this branch changes no tailnet code."
remote_ci: required
remote_ci_evidence: Pending CI on the pull request, including the watchdog Molecule scenarios.
dry_run: required
dry_run_evidence: Pending dry-run of the affected nodes after merge.
staging: not_applicable
staging_evidence: The watchdog change reaches the existing nodes through the ordinary deploy transaction; the script changes run on the operator workstation.
live: required
live_evidence: Pending deploy and one alert through an operator-chosen destination.
client: not_applicable
client_evidence: No client payload changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-SEC-NAD-PRIVATE-ALERTS | SEC-1794728786307882 | `test_watchdog_templates.py` (default destination, alias, production refusal), `test_watchdog_notification.py` (provider none sends nothing), `test_ntfy_curl_config.py`, `test_monitor_reality_target.py` (argument list has no topic or token); Molecule and a live alert pending | required |
| REQ-SEC-NAD-BURN-CHECK-LOCAL | SEC-1794728798422428 | `test_burn_check_metrics.py`: default run calls no service and sends no UDP datagram, options are explicit, the cron entry and the Make recipe pass none | passed |
| REQ-SEC-NAD-ENCRYPTED-LOOKUPS | SEC-1794728810946200 | `test_doh_lookup.py`: lookups reach only the loopback resolver, fail closed without it, refuse a redirect, and an unmeasured block list is not clean | passed |
| REQ-SEC-NAD-PRIVATE-REPORTS | SEC-1794728832615527 | `test_diagnostic_host_scope.py`: report is outside the repository, mode 0600, no address in the name | passed |
| REQ-SEC-NAD-TRACKED-ADDRESS-GUARD | SEC-1794728832615527 | `test_repository_identifier_policy.py`: scan unit case and the tracked-file check | passed |
