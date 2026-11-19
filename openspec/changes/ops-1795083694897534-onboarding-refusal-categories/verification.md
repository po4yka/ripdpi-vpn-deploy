---
task_id: OPS-1795083694897534
change: ops-1795083694897534-onboarding-refusal-categories
commit_sha: 248f21e4e3328635d3af2ac1d19c5d84a61fb47a
local: passed
local_evidence: "make -k -j 4 check under mise on the implementation tree: every target passed except test-unit (12227 passed, 1 failed). The failure was test_observability_deadman_receiver::test_worker_capacity_is_bounded_before_tls_and_reclaimed_after_deadline (ConnectionResetError under parallel load), a module this change does not touch; it passed 3/3 alone. After the review fixes (dead path-refused reason removed, emitter input wording) test_sshd_baseline_controller and test_recovery_promotion passed (117), make docs-check passed and openspec validate --strict passed. The narrow suites for every touched module passed (410). One independent review: no blocking defects; two low findings fixed or recorded (wording; per-layer rather than single end-to-end test)."
remote_ci: passed
remote_ci_evidence: "PR 643 merged by rebase at 2026-11-19T12:20:41Z as 248f21e4 (fix) and a9592f19 (review snapshot) after a rebase onto 9146f679. Main CI run 44523008717 on a9592f19 passed on attempt 1 with 84 of 84 jobs successful."
dry_run: not_applicable
dry_run_evidence: Check mode does not require or write a baseline failure receipt, so a dry-run cannot exercise the changed reason.
staging: not_applicable
staging_evidence: The change alters only failure-path diagnostics; reproducing it on staging needs a deliberately failing deploy, and the local tests run the same code paths.
live: not_applicable
live_evidence: No runtime, host or network behavior changes; only the categorical reason of a private failure receipt changes.
client: not_applicable
client_evidence: Successful client payloads are unchanged; only refusal stderr changes.
artifact: not_applicable
artifact_evidence: No release artifact changes.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DR-ONBOARDING-RECEIPT | OPS-1795083969470810 | test_sshd_baseline_controller::test_promotion_refusal_category_reaches_the_failure_receipt | passed |
| REQ-DR-ONBOARDING-PAYLOAD | OPS-1795083969470810 | test_emit_singbox_roundtrip::test_unavailable_terraform_endpoint_reports_its_fixed_category, test_install_liveness_sentinel::test_emitter_refusal_reports_only_its_fixed_category, test_recovery_promotion::test_installer_refusal_keeps_only_fixed_payload_categories | passed |
| REQ-DR-ONBOARDING-PRIVATE | OPS-1795083982510317 | test_fleet_inspection::test_command_input_stderr_and_exit_are_bounded, test_install_liveness_sentinel::test_emitter_refusal_reports_only_its_fixed_category[workspace missing at /private/path-command-failed], test_sshd_baseline_controller::test_promotion_refusal_category_reaches_the_failure_receipt[recovery-promotion-unlisted-category-onboarding-refused] | passed |
