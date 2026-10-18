# OPS-1792263187492070: Restore deployment and VPN rollback reliability

## Objective

Repair the six audited failure paths and merge verified source without a live rollout.

## Ownership

- deploy_audit owns scripts/blue-green.sh, scripts/ci-real-deploy.py, the narrow scripts/bootstrap_readiness.py stderr API, tests/unit/test_ci_real_deploy.py, tests/unit/test_bootstrap_readiness_io.py, tests/unit/test_audit_operator_paths.py, tests/bats/blue_green_dryrun.bats and dedicated blue-green regressions.
- deploy_audit also owns tests/unit/test_runtime_awg_profile.py plus tests/unit/test_transport_site_transaction.py and tests/unit/test_runtime_source_consumers.py source-contract adaptations; vpn_audit owns its production implementation.
- infra_audit owns scripts/backup-tf-state.sh, docs/RUNBOOK-incident.md and tests/unit/test_tf_state_backup.py.
- infra_audit also owns tests/native/transport_acceptance/test_awg_lifecycle.py and tests/unit/test_awg_activation_native.py native fixture adaptations and exact supporting dependency maps; vpn_audit retains production/helper ownership.
- infra_audit owns tests/unit/test_awg_native_renderer.py and the native fixture expected-render correction; production and the generic snapshot renderer retain their current contracts.
- infra_audit owns tests/unit/test_topology_awg_warm_native.py migration to the complete publisher, retaining real process, sandbox, binary, unit, and unchanged-convergence assertions.
- infra_audit owns tests/unit/test_awg_warm_diagnostics.py and fixed-category warm failure evidence; primary owns the early native warm and complete AWG rollback CI steps and tests/unit/test_executable_coverage.py wiring guards. The complete native suite and its gates remain required.
- vpn_audit owns ansible/playbooks/site.yml and required playbook tasks, ansible/roles/firewall, ansible/roles/amneziawg, the required runtime-release retention seam, owned role notes and focused VPN tests.
- vpn_audit also owns the narrow ansible/roles/baseline/tasks/forwarding.yml retained-forwarding seam, its CLAUDE.md note and focused forwarding regressions; standalone baseline keeps its current contract.
- vpn_audit owns the CI-confirmed inline command rendering fix and the fresh missing-unit restore guard in nginx_transaction.py with tests/unit/test_nginx_site_transaction.py; shared ownership is serialized before the next source freeze.
- deploy_audit owns only the fields() target-property correction in ansible/roles/amneziawg/files/consumer.py and tests/unit/test_awg_unit_state.py; vpn_audit will not edit that function or test during the CI repair.
- deploy_audit owns the three acquisition-loop no_log additions in amneziawg/tasks/configure.yml and the child-tag contract adaptation in tests/unit/test_warp_pin_contract.py; existing privacy assertions remain unchanged.
- vpn_audit owns the retained-consumer check-mode and pre-mutation contract adaptations in tests/unit/test_check_mode_handlers.py, tests/unit/test_transport_semantics.py and its existing test_vpn_consumer_reliability.py lane.
- infra_audit owns the explicitly authorized CI-only Debian13 publisher run, all 45 Debian13 Molecule pin files and tests/unit/test_molecule_image_pins.py. Accept only a freshly scanned immutable digest; primary serializes commits and publication of the PR branch.
- deploy_audit owns the exact runtime-authority fixture dependency in tests/unit/test_amneziawg_source_pins.py.
- vpn_audit owns tests/unit/test_fresh_protocol_check_mode.py for the retained AWG fresh-host check-mode contract; Hysteria checks remain unchanged.
- infra_audit owns the hosted-runner trusted executable parent setup in .github/actions/setup-disposable-ci/action.yml and its executable regression; production trust checks stay unchanged.
- vpn_audit owns the six confirmed CodeQL repairs in its consumer helpers, reliability/profile tests and the unused initial warm acquisition binding; the acquisition call remains required.
- primary owns tests/conftest.py fixture group normalization and serializes shared scripts/CLAUDE.md, tests/CLAUDE.md, ansible/CLAUDE.md, docs/RUNBOOK-deploy.md, task/spec artifacts, integration and Git/PR operations. Workers do not commit or edit shared lanes.

## Execution

- [x] OPS-1792263261040276 Serialize blue-green phases and preserve dry-run intent with regression tests #bug !high @item:OPS-1792263187492070
- [x] OPS-1792263261891666 Isolate state backup retention and recovery by exact environment with regression tests #bug !high @item:OPS-1792263187492070
- [ ] OPS-1792263262980365 Compensate firewall and retain complete AWG runtime through acceptance with regression tests #bug !high @item:OPS-1792263187492070
- [x] OPS-1792263263700589 Reclaim CI command descendants with retained supervisor and regression tests #bug !high @item:OPS-1792263187492070
- [ ] OPS-1792263264479573 Run required gates and reviews and land the verified pull request #bug !high @item:OPS-1792263187492070

## Verification

Focused pytest and Bats regressions, shellcheck, snapshot-check, applicable Molecule and native hosted acceptance, make check, security review and structured autoreview. Remote CI must pass for the reviewed source. No external staging, live hosts or recipient devices are in scope.
