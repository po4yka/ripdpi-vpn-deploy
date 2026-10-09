# TFR-1791523370274374: Fix provider management isolation and provisioning blockers

## Objective

Deliver all actionable P1 and P2 provider audit repairs with safe positive
behavior and regression coverage in PR 281; retain infrastructure evidence gaps.

## Ownership

- Management worker owns terraform/providers/*/variables.tf, the two Hetzner
  environments/*.tfvars.example files and tests/management.tftest.hcl in each root.
- Lifecycle worker owns main.tf under hetzner, vultr and scaleway, Hetzner
  firewall.tf, new provider lifecycle/migration native fixtures and
  tests/unit/test_provider_bootstrap_lifecycle.py.
- Primary owns Makefile, .pre-commit-config.yaml, .github/workflows/tf-policy.yml, terraform/policy/*, scripts/tf-policy-test.sh,
  scripts/terraform-plan-policy.py, scripts/policy-plan.sh, scripts/check-tf-plan.sh,
  tests/unit/test_terraform_plan_policy.py, tests/unit/test_terraform_apply_policy.py,
  provider README generation, subtree CLAUDE.md updates and all task/spec metadata.
- Workers share this dedicated worktree. Only primary writes shared guidance,
  metadata, integration changes and commits. Heavy checks use build-gate once.

### Integration ownership

- Policy worker resolves terraform/policy/{admin_port,ssh_cidrs,secondary_ip,
  secondary_ip_test}.rego and consolidates port semantics into the incoming
  canonical firewall.rego/firewall_test.rego helper API.
- Primary resolves Makefile, scripts/tf-policy-test.sh and tf-policy.yml,
  consolidates operator gates into check-tf-plan.sh/policy-plan.sh, owns evaluator
  and gate-test updates, guidance, metadata and merge commit.
- Lifecycle worker validates provider lifecycle/native tests against incoming
  bootstrap-seed changes; reports integration gaps without editing shared lanes.

## Execution

- [x] TFR-1791523579427434 Reject unsafe management CIDRs and effective TCP listener collisions with positive native coverage #bug !high @item:TFR-1791523370274374
- [x] TFR-1791523580174419 Restore Hetzner provisioning and guard immutable bootstrap identity with migration and transition coverage #bug !high @item:TFR-1791523370274374
- [x] TFR-1791523580836950 Enforce exact saved-plan policy evaluation and range-aware management rules with positive and refusal coverage #bug !high @item:TFR-1791523370274374
- [x] TFR-1791523581450706 Run complete local gate and independent security review, then publish the scoped PR #bug !high @item:TFR-1791523370274374

## Verification

- Local: four complete native suites, Conftest verify, targeted pytest and full
  build-gate -- mise exec -- make check, followed by independent security review.
- Remote CI and artifact: exact committed PR head and hosted checks.
- Dry-run, staging, live and client checks: outside the authorized PR scope.

## P2 ownership and execution

- Lifecycle worker: Vultr main.tf, firewall.tf and new provider-adapter.tftest.hcl.
- Port worker: all four variables.tf, firewall.tftest.hcl and new
  port-validation.tftest.hcl files.
- Primary: shared cloud-init, render-cloud-init-ci.py, serialization tests,
  test_executable_coverage.py native-test registration,
  generated READMEs, subtree guidance, all planning, integration and commits.
  The encoded-scalar integration also requires primary's narrow Scaleway main.tf
  retained-key normalization; lifecycle worker owns the Vultr equivalent.
- Workers are not alone in this worktree; preserve peer edits and do not commit.

- [x] TFR-1791537004741307 Repair Vultr range encoding and enable-backups schedule with positive adapter plans #bug @item:TFR-1791523370274374
- [x] TFR-1791537005304551 Reject fractional listener ports and exercise actual legacy XHTTP deduplication in all roots #bug @item:TFR-1791523370274374
- [x] TFR-1791537005854827 Encode shared cloud-init scalar inputs and preserve literal metadata across renderers #bug @item:TFR-1791523370274374
- [ ] TFR-1791537006373613 Validate P2 integration and independent review and publish exact-head evidence on PR 281 #bug @item:TFR-1791523370274374
