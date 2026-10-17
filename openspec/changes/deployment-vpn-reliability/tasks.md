# OPS-1792263187492070: Restore deployment and VPN rollback reliability

## Objective

Repair the six audited failure paths and merge verified source without a live rollout.

## Ownership

- deploy_audit owns scripts/blue-green.sh, scripts/ci-real-deploy.py, the narrow scripts/bootstrap_readiness.py stderr API, tests/unit/test_ci_real_deploy.py, tests/unit/test_bootstrap_readiness_io.py, tests/unit/test_audit_operator_paths.py, tests/bats/blue_green_dryrun.bats and dedicated blue-green regressions.
- deploy_audit also owns tests/unit/test_runtime_awg_profile.py plus tests/unit/test_transport_site_transaction.py and tests/unit/test_runtime_source_consumers.py source-contract adaptations; vpn_audit owns its production implementation.
- infra_audit owns scripts/backup-tf-state.sh, docs/RUNBOOK-incident.md and tests/unit/test_tf_state_backup.py.
- infra_audit also owns tests/native/transport_acceptance/test_awg_lifecycle.py and tests/unit/test_awg_activation_native.py native fixture adaptations and exact supporting dependency maps; vpn_audit retains production/helper ownership.
- vpn_audit owns ansible/playbooks/site.yml and required playbook tasks, ansible/roles/firewall, ansible/roles/amneziawg, the required runtime-release retention seam, owned role notes and focused VPN tests.
- vpn_audit also owns the narrow ansible/roles/baseline/tasks/forwarding.yml retained-forwarding seam, its CLAUDE.md note and focused forwarding regressions; standalone baseline keeps its current contract.
- primary owns tests/conftest.py fixture group normalization and serializes shared scripts/CLAUDE.md, tests/CLAUDE.md, ansible/CLAUDE.md, docs/RUNBOOK-deploy.md, task/spec artifacts, integration and Git/PR operations. Workers do not commit or edit shared lanes.

## Execution

- [x] OPS-1792263261040276 Serialize blue-green phases and preserve dry-run intent with regression tests #bug !high @item:OPS-1792263187492070
- [x] OPS-1792263261891666 Isolate state backup retention and recovery by exact environment with regression tests #bug !high @item:OPS-1792263187492070
- [ ] OPS-1792263262980365 Compensate firewall and retain complete AWG runtime through acceptance with regression tests #bug !high @item:OPS-1792263187492070
- [x] OPS-1792263263700589 Reclaim CI command descendants with retained supervisor and regression tests #bug !high @item:OPS-1792263187492070
- [ ] OPS-1792263264479573 Run required gates and reviews and land the verified pull request #bug !high @item:OPS-1792263187492070

## Verification

Focused pytest and Bats regressions, shellcheck, snapshot-check, applicable Molecule and native hosted acceptance, make check, security review and structured autoreview. Remote CI must pass for the reviewed source. No external staging, live hosts or recipient devices are in scope.
