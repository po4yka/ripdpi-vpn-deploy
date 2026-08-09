---
task_id: CIC-1786295418152915
change: integrate-zizmor-ci-security-gate
commit_sha: null
local: required
local_evidence: null
remote_ci: required
remote_ci_evidence: null
dry_run: not_applicable
dry_run_evidence: No infrastructure render or mutation is owned by this CI-only change.
staging: not_applicable
staging_evidence: No staged infrastructure behavior is owned by this CI-only change.
live: not_applicable
live_evidence: No live infrastructure behavior is owned by this CI-only change.
client: not_applicable
client_evidence: No VPN client behavior is owned by this CI-only change.
artifact: not_applicable
artifact_evidence: The change consumes a checksum-pinned analyzer but publishes no project artifact.
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-ZIZMOR-PIN | CIC-1786296210585916 | Exact mise pin, CI archive checksum, observed `zizmor --version`, and parity contract test | required |
| REQ-ZIZMOR-SCOPE | CIC-1786296210585916 | Scoped `.github` plus `.pre-commit-config.yaml` invocation and vendored-fixture exclusion test | required |
| REQ-ZIZMOR-FAIL-CLOSED | CIC-1786296210585916 | Strict regular-persona scan, negative fixture contract, `make ci-fast`, and required-job dependency | required |
| REQ-ZIZMOR-ZERO-BASELINE | CIC-1786296210350045 | Reusable Rust workflow focused tests and scoped analyzer | required |
| REQ-ZIZMOR-ZERO-BASELINE | CIC-1786296210412999 | Base-ref workflow focused tests and scoped analyzer | required |
| REQ-ZIZMOR-ZERO-BASELINE | CIC-1786296210451056 | Deployment workflow/Terraform contract tests and scoped analyzer | required |
| REQ-ZIZMOR-ZERO-BASELINE | CIC-1786296210479892 | Reproducible-pin contract tests and scoped analyzer | required |
| REQ-ZIZMOR-ZERO-BASELINE | CIC-1786296210502723 | Checkout credential-persistence contract tests and scoped analyzer | required |
| REQ-ZIZMOR-ZERO-BASELINE | CIC-1786296210530158 | Dependabot cooldown contract test and scoped analyzer | required |
| REQ-ZIZMOR-ZERO-BASELINE | CIC-1786296210558254 | Release asset/tag contract tests and scoped analyzer | required |
| REQ-ZIZMOR-LEAST-PRIVILEGE | CIC-1786296210502723 | No persisted checkout credentials across owned workflows | required |
| REQ-ZIZMOR-LEAST-PRIVILEGE | CIC-1786296210585916 | Offline no-token CI job with read-only permissions and temporary install | required |
| REQ-ZIZMOR-CANONICAL-GATE | CIC-1786296210585916 | `make zizmor-check`, `make ci-fast`, and local/CI invocation parity tests | required |
| REQ-ZIZMOR-ROLLBACK | CIC-1786296210585916 | Focused commit history, final diff review, and documented rollback boundary | required |
