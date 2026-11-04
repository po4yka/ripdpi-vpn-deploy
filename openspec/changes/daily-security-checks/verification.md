---
task_id: SEC-1793770690402026
change: daily-security-checks
commit_sha: bc9bf0d0fc9bea2d5ff20aa37e6c1aaf284f7429
local: blocked
local_evidence: "Feature checks and Ubuntu native regressions pass; full macOS parity has confirmed baseline failures. See local results."
remote_ci: not_applicable
remote_ci_evidence: Source delivery only; no push or hosted run requested. Hosted execution is unverified.
dry_run: not_applicable
dry_run_evidence: No infrastructure transaction requested.
staging: not_applicable
staging_evidence: No staging deployment requested.
live: not_applicable
live_evidence: No fleet access or deployment requested.
client: not_applicable
client_evidence: VPN client behavior is unchanged.
artifact: not_applicable
artifact_evidence: No release artifact requested. Hosted scan artifacts and real notifications remain unverified.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DAILY-SCANS | SEC-1793771107840507 | Workflow/inventory regressions and real Trivy 0.70.0 scans | passed |
| REQ-DAILY-NOTIFY | SEC-1793771107840507 | Executable notification regressions with the GitHub API boundary replaced | passed |
| REQ-AUDIT-SYSTEMD | SEC-1793771107840507 | Actual Ansible task execution with the analyzer process boundary replaced, on macOS and Ubuntu | passed |

## Local results

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

A complete credential-free parity run on Linux or hosted CI remains unverified.
Keep this change in review; do not treat these results as full-gate, deployment
or notification-delivery acceptance.
