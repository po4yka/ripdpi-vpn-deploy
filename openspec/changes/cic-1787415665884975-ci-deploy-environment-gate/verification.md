---
task_id: "CIC-1787415665884975"
change: "cic-1787415665884975-ci-deploy-environment-gate"
commit_sha: "984b4528b634b4b48fa74fac0b4cbb22b8b7b887"
local: "passed"
local_evidence: "Full build-gate -- make -j1 check passed under umask 077: 1024 Python tests passed, 1 existing live-scanner placeholder skipped; 55 BATS; 173 Rust release tests; 79 Terraform mocks; 102 snapshots. Release clippy, Rust 1.88 MSRV, cargo deny, Docker cloud-init schema, make validate, lint/render/schema gates passed. Separate Rust debug suite: 173 passed."
remote_ci: "passed"
remote_ci_evidence: "PR #108, exact implementation SHA 984b4528b634b4b48fa74fac0b4cbb22b8b7b887: CI run 33069634871 completed success; 62 successful checks and one neutral Trivy SARIF report, with both image scan jobs successful. All required checks and expanded hosted Molecule scenarios passed. This is PR evidence; protected main merge remains a delivery step."
dry_run: "not_applicable"
dry_run_evidence: "no deploy pipeline change; workflow YAML validated statically"
staging: "not_applicable"
staging_evidence: "gating is enforced by GitHub Environment settings, not by a deployable artifact"
live: "passed"
live_evidence: "make check-ci-deploy-gate passed again on exact source 984b4528b634b4b48fa74fac0b4cbb22b8b7b887: GitHub environment API confirms required-reviewer protection. No deployment dispatched; CI operator secrets were not provisioned or changed."
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

### Final checks on the reviewed implementation

- `build-gate -- make -j1 check` passed under restrictive umask 077: Python 1024 passed, 1 existing unconditional live-scanner placeholder skipped; BATS 55 passed; Rust release 173 passed; Terraform mocks 79 passed; 102 snapshots matched.
- Release clippy, Rust 1.88 locked MSRV, cargo deny, cloud-init schema in Docker, and all render/schema/lint gates passed. `make validate` also passed after the final role edit. Rust debug independently passed 173 tests.
- [Hosted CI run 33069634871](https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/33069634871) passed on `984b4528b634b4b48fa74fac0b4cbb22b8b7b887`. PR #108 has 62 successful checks and one neutral Trivy SARIF report; both image scan jobs succeeded. Expanded Molecule scenarios executed on hosted amd64 Linux.
- Earlier umask, role runtime, fixture, and container validation failures are superseded by these successful reruns. Local amd64 systemd Molecule on this arm64 Mac remains unavailable (`pidfd_open` ENOSYS); hosted Molecule is the observed role-runtime evidence, not production evidence.
- Existing cargo-deny duplicate-dependency warnings and one workflow line-length warning remain. The skipped live scanner test is not counted as acceptance.

## Approval-gate acceptance

make check-ci-deploy-gate passed again on exact source 984b4528b634b4b48fa74fac0b4cbb22b8b7b887: GitHub environment API confirms required-reviewer protection. No deployment dispatched; CI operator secrets were not provisioned or changed.

All required evidence categories are complete. This does not claim a credentialed deployment.
