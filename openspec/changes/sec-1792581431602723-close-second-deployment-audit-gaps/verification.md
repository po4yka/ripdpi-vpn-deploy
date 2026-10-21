---
task_id: SEC-1792581431602723
change: sec-1792581431602723-close-second-deployment-audit-gaps
commit_sha: pending
local: passed
local_evidence: Each new regression fails on its parent commit and passes after its fix: 32 vpnd step-signal cases on e0b12c1d, 9 cleanup-signal and nohup cases on 56edaf20, the Vultr os_change run on e0b12c1d, 21 verification-play cases on 0324c104 and 2 Hetzner key refusals on 491f2850. On 12949e0f make tf-test, vpnd-test, vpnd-lint, vpnd-parity-check, validate, shellcheck, snapshot-check, tf-policy-verify and task-check passed. make test-unit ran 9232 passed with 6 failed and 70 errors, all in five files whose isolated-HOME tests need real sops and sing-box; the main checkout resolves them to mise shims without a version. The same head passes test_naive_device_operations.py and test_retire_unbound_staging_client.py (156 passed) in a separate worktree. test_smoke_test_cleanup.py (58) passed on 94abe1ba. Docker-dependent cloud-init schema and Molecule did not run locally. Independent review found 3 medium and 4 low findings; fixed in 9a2bd9b5 and 12949e0f except the fail-open Hetzner key parse, which Terraform still refuses at apply.
remote_ci: required
remote_ci_evidence: PR #352 CI run 39611311596 passed all 92 jobs on 94abe1ba01ea356f3838f09f2ddbe5a2c8b1c5f4, including pytest groups 1-4 on Linux, Molecule and native lanes. Run 39605489408 on 12949e0f failed only test_smoke_test_cleanup.py on Linux (fact gathering called the harness systemctl stub), fixed in 94abe1ba. Protected main CI on the merge commit is still required.
dry_run: not_applicable
dry_run_evidence: The change does not modify the deploy controller or rendered deployment input. The verification plays, vpnd pipeline and provider roots are source fixes covered by local and CI regressions.
staging: not_applicable
staging_evidence: No staging rollout is included.
live: not_applicable
live_evidence: No provider, host, credential or production operation is included.
client: not_applicable
client_evidence: No client payload, bundle or recipient contract changes.
artifact: passed
artifact_evidence: With Terraform built-in resources, a newly created replace trigger does not replace an existing resource, while a later change does; a trigger to an absent counted instance, indexed or not, fails every plan with no change found, which rejected the Hetzner named-key design. Vultr documents an os_id change as an in-place update that wipes the server.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DAB-SIGNAL | SEC-1792581854245311 | test_signal_during_a_step_still_cleans_plaintext (32); test_signal_during_cleanup_reports_the_signal (8); test_an_ignored_hangup_stays_ignored_for_every_step | passed |
| REQ-DAB-OSIMAGE | SEC-1792581855014542 | vultr lifecycle run os_change_refuses_in_place_reinstall; make tf-test | passed |
| REQ-DAB-PLAYENV | SEC-1792581856404337 | test_verification_play_* (21 real Ansible and make -n cases); test_smoke_test_cleanup.py | passed |
| REQ-DAB-SHAREDKEY | SEC-1792581857264775 | test_hetzner_green_with_the_blue_key_refuses_before_plan (2); test_hetzner_green_with_its_own_key_provisions | passed |
| All | SEC-1792581857974419 | Local gates above; independent review; PR #352 CI run 39611311596 | passed |
