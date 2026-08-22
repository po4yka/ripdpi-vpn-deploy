---
task_id: CIC-1787415665884975
change: cic-1787415665884975-ci-deploy-environment-gate
commit_sha: null
local: passed
local_evidence: pytest tests/unit/test_credentialed_deploy_gate_contract.py (3 passed), pytest tests/unit/test_probe_matrix_provisioning.py (6 passed), actionlint on both workflows (clean), make validate green after provider init
remote_ci: blocked
remote_ci_evidence: pending required checks on PR #83 (audit-critical-fixes); record SHA and run on merge
dry_run: not_applicable
dry_run_evidence: no deploy pipeline change; workflow YAML validated statically
staging: not_applicable
staging_evidence: gating is enforced by GitHub Environment settings, not by a deployable artifact
live: passed
live_evidence: GET /repos/po4yka/ripdpi-vpn-deploy/environments/ci-real-deploy returns protection_rules [required_reviewers] with reviewer po4yka (id 42894392)
client: not_applicable
client_evidence: no client-facing surface changed
artifact: not_applicable
artifact_evidence: no build artifacts produced by this change
---

# Verification

## Requirement evidence

| Requirement | Execution step | Evidence | Result |
|---|---|---|---|
| REQ-DEPLOY-GATE | CIC-1787416554747959 | `gh api repos/po4yka/ripdpi-vpn-deploy/environments/ci-real-deploy` shows `protection_rules[type=required_reviewers]`; both jobs carry `environment: ci-real-deploy` | Passed |
| REQ-DEPLOY-GATE | CIC-1787416554748223 | `test_credentialed_jobs_reference_the_protected_environment` passes; approval now applies to label, dispatch, and schedule triggers | Passed |
| REQ-DEPLOY-GATE-SECRETS | CIC-1787416554749284 | Both staging steps use step-level `env:` with quoted `$CI_SSH_PRIVATE_KEY` / `$CI_SOPS_AGE_KEY`; `test_no_secret_is_expanded_inside_run_blocks` passes | Passed |
| REQ-DEPLOY-GATE-DEFENSE | CIC-1787416554748223 | "Refuse to run on a fork PR" steps retained in both workflows; asserted by `test_fork_short_circuit_is_retained` | Passed |
| Contract regression guard | CIC-1787416554750572 | `python3 -m pytest tests/unit/test_credentialed_deploy_gate_contract.py -q` — 3 passed | Passed |
| Local gates | CIC-1787416554751856 | actionlint clean; `make validate` green (terraform fmt+validate x4, gitleaks history+staged, ansible-lint production profile, site.yml syntax check) | Passed |

## Notes

- `remote_ci` stays `blocked` until PR #83 completes its required checks; the
  exact merged SHA is recorded here before archive.
- The environment approval intentionally adds a manual step to every
  credentialed run including the weekly schedule; `can_admins_bypass` remains
  enabled for the solo maintainer.
