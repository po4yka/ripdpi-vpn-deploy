# CIC-1787415665884975: Gate credentialed CI deploys behind environment approval

## Objective

A `ci-real-deploy` label, `workflow_dispatch`, or scheduled trigger can no
longer reach provider credentials or CI key material without an approved
GitHub deployment: both credentialed jobs run behind the protected
`ci-real-deploy` environment, deploy key material reaches the shell only
through step-level `env:`, and both invariants are contract-tested.

## Ownership

- The primary agent owns `.github/workflows/real-vps-deploy.yml`,
  `.github/workflows/transport-reachability-matrix.yml`,
  `tests/unit/test_credentialed_deploy_gate_contract.py`, and this change's
  task/evidence files.
- Repository settings (GitHub Environment provisioning) are serialized through
  the GitHub API and recorded in verification evidence.

## Execution

- [x] CIC-1787416554747959 Provision the `ci-real-deploy` GitHub Environment with a required-reviewer protection rule through the GitHub API so a workflow reference never auto-creates an unprotected environment #bug !high @item:CIC-1787415665884975
- [x] CIC-1787416554748223 Reference the `ci-real-deploy` environment on the credentialed jobs of `real-vps-deploy.yml` and `transport-reachability-matrix.yml` while retaining the fork short-circuit steps #bug !high @item:CIC-1787415665884975
- [x] CIC-1787416554749284 Stage `CI_SSH_PRIVATE_KEY` and `CI_SOPS_AGE_KEY` through step-level `env:` indirection in both "Stage SSH key + age key + CI tfvars" steps, removing direct `${{ secrets.* }}` expansion from `run:` blocks #bug !high @item:CIC-1787415665884975
- [x] CIC-1787416554750572 Add `tests/unit/test_credentialed_deploy_gate_contract.py` asserting environment gating, absence of `${{ secrets.` inside `run:` blocks, and retained fork short-circuits #test !high @item:CIC-1787415665884975
- [x] CIC-1787416554751856 Run the named local gates: focused pytest contract tests, actionlint on both workflows, and `make validate` #test !high @item:CIC-1787415665884975

## Verification

Use the exact gates and evidence categories in `verification.md`.
