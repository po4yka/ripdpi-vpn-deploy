# MON-1791825755591250: Repair alert delivery and service monitoring

## Objective

Repair the audited alerting defects with executable producer/consumer regressions and a source-only PR.

## Ownership

- Relay worker: observability-telegram-relay.py and test_observability_telegram_delivery.py; canary sequence regression and existing delivery boundary verification. Local gate repairs also own tests/unit/test_observability_control_plane_alerting.py for isolated authority transaction fixtures.
- Monitoring worker: observability_agent role and its tests, monitoring audit regressions; latest-head failed native agent scenario diagnosis and correction.
- Gate fixture worker: tests/unit/test_cascade_roles.py and tests/unit/test_deploy_controller.py; isolated local Ansible paths and complete transaction budgets.
- Bounded I/O worker: scripts/bootstrap_readiness.py and tests/unit/test_bootstrap_readiness_io.py; preserve output refusal through exited-child process-group cleanup.
- Operator I/O worker: scripts/fleet_inspection.py and tests/unit/test_fleet_inspection.py; retry transient nonblocking pipe backpressure within existing deadlines and byte limits.
- Observer worker: observability_kuma role and tests; interrupted backup recovery verification and scoped corrections. Local gate repairs also own tests/unit/test_runtime_release_contract.py and tests/unit/test_xray_runtime_mode_transition.py for temporary-root group contracts.
- Primary: scripts/observability-operator.py, operator tests and scripts notes, collector notes, planning/task lifecycle, operator docs, reviewed snapshots, final gates, commits and PR.
- Shared task state, documentation and snapshot edits are serialized by the primary after worker source changes. Workers do not commit, stage or push. All workers preserve concurrent edits and use the machine build gate for heavy validation.

## Execution

- [x] MON-1791825842898373 Repair Telegram payload and response boundaries with realistic regressions #bug !high @item:MON-1791825755591250
- [x] MON-1791825843454772 Repair evidence parsing, producer freshness and expected coverage #bug !high @item:MON-1791825755591250
- [x] MON-1791825844021163 Restore independent observer after backup interruptions #bug !high @item:MON-1791825755591250
- [ ] MON-1791825844572081 Validate all fixes, independently review and prepare source-only PR #bug !high @item:MON-1791825755591250

## Verification

Focused Telegram/observer and evidence/service tests; actual producer-output and pinned promtool failure/recovery boundaries; reviewed snapshot refresh/check; affected default/enabled Molecule and observer interruption scenarios; full build-gated mise exec -- make check; independent security review; exact-source PR checks. No real inventory, host, provider, credential or Telegram actions. Local/source CI evidence cannot close the existing live rollout task.
- [x] MON-1791873973944403 Recover delivery canaries after ambiguous upstream acknowledgement #bug !high @item:MON-1791825755591250
- [x] MON-1791873974708567 Make operator drills satisfy the relay contract and verify API delivery #bug !high @item:MON-1791825755591250
