---
task_id: SEC-1793770690402026
change: daily-security-checks
commit_sha: 4a980d5a883c9049d693df6caade98e920e4c7f6
local: blocked
local_evidence: "Feature checks and Ubuntu native regressions pass; full macOS parity has confirmed baseline failures. See local results."
remote_ci: blocked
remote_ci_evidence: "At the 2026-11-04 refresh, merged-source CI run 41807153081 had not completed and daily-security had no runs. Hosted daily scan execution and notification delivery remain unverified."
dry_run: not_applicable
dry_run_evidence: "No full site transaction. The separate audit playbook passed check-mode preview on all three approved VPN nodes before apply."
staging: not_applicable
staging_evidence: No separate disposable staging acceptance was performed for this report-only audit.
live: passed
live_evidence: "Authorized security_audit apply and direct report readback passed on node-a, node-b and node-c from fdb0f760827a4adffa3032d1fe0da5d104b5acdc. The role matches the merged source. Scope is report collection, not core deployment or client acceptance."
client: not_applicable
client_evidence: No new authenticated client-traffic test was performed; the audit does not publish VPN configuration.
artifact: blocked
artifact_evidence: "Fresh private host reports are verified. No complete hosted daily SARIF and image-inventory artifact set has been observed."
---

# Verification

## Source and evidence scope

This record covers merged source `4a980d5a883c9049d693df6caade98e920e4c7f6`.
The initial local checks below ran at
`bc9bf0d0fc9bea2d5ff20aa37e6c1aaf284f7429`. The later audit correction and live
apply used `fdb0f760827a4adffa3032d1fe0da5d104b5acdc`; its role and playbook
files match the merged source. No whole-service source revision is advanced by
this operator-run audit.

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DAILY-SCANS | SEC-1793771107840507 | Local workflow/inventory regressions and real Trivy scans passed; scheduled/manual workflow execution and its complete artifact set are unverified | blocked |
| REQ-DAILY-NOTIFY | SEC-1793771107840507 | Executable notification regressions passed with the GitHub API boundary replaced; actual owner issue updates and notification delivery are unverified | blocked |
| REQ-AUDIT-SYSTEMD | SEC-1793771107840507 | Corrected argument regressions, actual analyzer execution and fresh private report readback on all three approved VPN nodes | passed |

## Local results

These are the initial implementation checks, not hosted delivery or live proof.

- The four feature test files passed all 52 cases with the repository Ansible
  configuration. Tests cover changed/unchanged results, complete recovery,
  invalid reports, stale revisions, previous attempts and analyzer failure/check mode.
- The existing Ubuntu 24.04 arm64 container, with OpenSSH 9.6 and hash-locked
  Python dependencies in a private directory, passed all 310 cases in
  `test_sshd_ownership.py`, `test_sshd_migrate.py`, `test_evidence_ssh_admission.py`,
  `test_watchdog_templates.py` and `test_audit_improvement_host_contracts.py`.
  These are isolated local tests, not fleet or live SSH acceptance.
- Real checksum-verified Trivy 0.70.0, the pinned action's runtime version,
  scanned all five dependency manifests and reported three Go advisories.
  Its separate clean vpnd scan produced an empty SARIF result array, accepted
  by the notification parser. No findings were suppressed or dependencies updated.
- actionlint, strict offline zizmor, the changed Ansible task's production lint,
  the new Python test's Ruff check, and whitespace checks passed.
- Independent structured source review and its secret scan completed without
  accepted P0 findings. No hosted execution or notification delivery is claimed.

## Authorized host audit and correction

The owner later approved source publication and the separate audit on the three
existing VPN nodes. The first live run retained `rc=1` and zero assessed units:
`--no-legend` is not supported by the `security` command. The process replacement
in the initial local tests did not validate this native CLI restriction.

The correction removed that flag from the command and report header, and updated
the argument contract checks. All 32 cases in
`test_audit_improvement_host_contracts.py`, production ansible-lint, commit hooks
and `make task-check` passed at the correction. The real corrected command also
completed successfully on each host before the role was reapplied.

The corrected role passed check-mode preview and `make security-audit` on the
frozen approved inventory. Direct readback verified fresh nonempty assessments,
successful analyzer return codes and `root:root` mode-0640 reports. The
[dated deployment update](../../../docs/reference/deployment-status.md#security-reporting-update-2026-11-04)
owns the host counts, Lynis warning counts and pre/post state observations.
Raw failed-attempt and successful evidence are encrypted and indexed in the
private operator kit. This proves report collection, not a clean-security verdict.

## Hosted workflow gap

Both implementation PRs are merged. At this refresh, the default-branch daily
workflow was active but had no runs. The
[merged-source CI run](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/41807153081)
had not completed; the final PR CI run was cancelled. No complete hosted daily
artifact set or actual notification issue update is claimed. Local tests that
replace the GitHub API cannot establish either result.

## Full-gate gap

`build-gate -- mise exec -- make -k -j 4 check` did not pass on macOS. The
initial liveness version mismatch passed when rerun with checksum-verified
sing-box 1.14.3 and Xray 26.10.31 in a temporary path. Native SSH policy and
Bash-dependent watchdog failures reproduced in a clean archive of baseline
`d6c19565ba906a20335dbf3b8a810c3de8d59442`; those files then passed in Ubuntu.
The initial full unit run was interrupted near completion after 11,435 passes
and 52 failures, including three new test-environment failures fixed by an
explicit non-privileged test play. The fixed audit file passed all 32 cases
with the Make Ansible configuration and in Ubuntu.

A complete credential-free parity run on Linux or hosted CI remains unverified
at this refresh. Keep this change in review while daily scan artifacts and actual
notification delivery remain unverified. The separately accepted host reports do
not establish full-gate, core deployment, protocol/client or whole-fleet acceptance.
