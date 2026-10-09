# TFR-1791523370274374: Fix provider management isolation and provisioning blockers

## Objective

Deliver all six P1 provider audit repairs with safe positive behavior, regression
coverage and a scoped PR; retain explicit gaps for infrastructure acceptance.

## Ownership

- Management worker owns terraform/providers/*/variables.tf, the two Hetzner
  environments/*.tfvars.example files and tests/management.tftest.hcl in each root.
- Lifecycle worker owns main.tf under hetzner, vultr and scaleway, Hetzner
  firewall.tf, new provider lifecycle/migration native fixtures and
  tests/unit/test_provider_bootstrap_lifecycle.py.
- Primary owns Makefile, .pre-commit-config.yaml, .github/workflows/tf-policy.yml, terraform/policy/*, scripts/tf-policy-test.sh,
  scripts/terraform-plan-policy.py, scripts/apply-terraform-plan.sh,
  tests/unit/test_terraform_plan_policy.py, tests/unit/test_terraform_apply_policy.py,
  provider README generation, subtree CLAUDE.md updates and all task/spec metadata.
- Workers share this dedicated worktree. Only primary writes shared guidance,
  metadata, integration changes and commits. Heavy checks use build-gate once.

## Execution

- [x] TFR-1791523579427434 Reject unsafe management CIDRs and effective TCP listener collisions with positive native coverage #bug !high @item:TFR-1791523370274374
- [x] TFR-1791523580174419 Restore Hetzner provisioning and guard immutable bootstrap identity with migration and transition coverage #bug !high @item:TFR-1791523370274374
- [x] TFR-1791523580836950 Enforce exact saved-plan policy evaluation and range-aware management rules with positive and refusal coverage #bug !high @item:TFR-1791523370274374
- [ ] TFR-1791523581450706 Run complete local gate and independent security review, then publish the scoped PR #bug !high @item:TFR-1791523370274374

## Verification

- Local: four complete native suites, Conftest verify, targeted pytest and full
  build-gate -- mise exec -- make check, followed by independent security review.
- Remote CI and artifact: exact committed PR head and hosted checks.
- Dry-run, staging, live and client checks: outside the authorized PR scope.
