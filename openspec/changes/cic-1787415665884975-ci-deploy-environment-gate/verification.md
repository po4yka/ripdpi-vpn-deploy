---
task_id: "CIC-1787415665884975"
change: "cic-1787415665884975-ci-deploy-environment-gate"
commit_sha: "bbc346415f412ab49f296db3927ff0fbefdaa8e0"
local: "blocked"
local_evidence: "2026-08-27: Rust debug/release each passed 173 tests, clippy/MSRV/deny passed; make validate and cloud-init schema passed. Full make check found two existing AWG installer fresh-directory failures under umask 077; root-cause correction and a complete rerun are pending."
remote_ci: "blocked"
remote_ci_evidence: "PR #108 is published. Expanded hosted Molecule coverage exposed runtime and scenario defects; final required-check success and main merge are still pending."
dry_run: "not_applicable"
dry_run_evidence: "no deploy pipeline change; workflow YAML validated statically"
staging: "not_applicable"
staging_evidence: "gating is enforced by GitHub Environment settings, not by a deployable artifact"
live: "passed"
live_evidence: "2026-08-27: make check-ci-deploy-gate read the GitHub environment API and verified required-reviewer protection. No deployment was dispatched and CI operator secrets are not provisioned."
client: "not_applicable"
client_evidence: "no client-facing surface changed"
artifact: "not_applicable"
artifact_evidence: "no build artifacts produced by this change"
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DEPLOY-GATE | CIC-1787416554747959 | `gh api repos/po4yka/ripdpi-vpn-deploy/environments/ci-real-deploy` shows `protection_rules[type=required_reviewers]`; both jobs carry `environment: ci-real-deploy` | Passed |
| REQ-DEPLOY-GATE | CIC-1787416554748223 | `test_credentialed_jobs_reference_the_protected_environment` passes; approval now applies to label, dispatch, and schedule triggers | Passed |
| REQ-DEPLOY-GATE-SECRETS | CIC-1787416554749284 | Both staging steps use step-level `env:` with quoted `$CI_SSH_PRIVATE_KEY` / `$CI_SOPS_AGE_KEY`; `test_no_secret_is_expanded_inside_run_blocks` passes | Passed |
| REQ-DEPLOY-GATE-DEFENSE | CIC-1787416554748223 | "Refuse to run on a fork PR" steps retained in both workflows; asserted by `test_fork_short_circuit_is_retained` | Passed |
| Contract regression guard | CIC-1787416554750572 | `python3 -m pytest tests/unit/test_credentialed_deploy_gate_contract.py -q` — 11 passed | Passed |
| Local gates | CIC-1787416554751856 | actionlint clean; `make validate` green (terraform fmt+validate x4, gitleaks history+staged, ansible-lint production profile, site.yml syntax check) | Passed |

## Notes

- The previous PR #83 evidence is superseded by the reviewed implementation SHA above.
- Environment metadata proves the approval rule exists; it is not proof of a credentialed deployment.
- Repository-level secrets are not isolated from a workflow that removes its environment reference. Deploy secrets should be environment-scoped; no settings or secrets were changed in this review.

## 2026-08-27 review

The original implementation was reopened after review found executable defects.
Local regressions do not substitute for the dry-run, staging, live, or hosted-CI categories above.
Archive and terminal closure remain blocked until all required evidence is complete.

### Shared local checks on the reviewed source

- `python3 -m pytest tests/unit -q`: 995 passed, 2 existing skips; one honeypot thread shutdown warning. The warning was reproduced only when the test fixture closes its listener while a daemon accept thread is running; it was not observed before cleanup. The stale collected-count documentation was corrected before this successful run.
- `bats tests/bats/`: 55 passed.
- `make tf-test`: 79 provider mock tests passed.
- `make snapshot-check`: 102 templates matched.
- `make validate`, actionlint, shellcheck, cargo-deny and Rust 1.88 MSRV check passed. YAML lint has one existing workflow line-length warning.
- Render, AWG version floor, Xray guards, secrets coverage, deploy-profile, example secrets schema and bundle schema checks passed.
- `make check` did not pass: its Docker cloud-init step lost the Colima connection. Per-role Molecule did not run. These checks must be rerun in a working container environment.
