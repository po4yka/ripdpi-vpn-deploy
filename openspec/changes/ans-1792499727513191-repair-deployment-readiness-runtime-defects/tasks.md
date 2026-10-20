# ANS-1792499727513191: Repair deployment readiness runtime defects

## Objective

Remove the five audited runtime defects (Xray rotation outage, resolvconf
resolver removal, AWG private-destination reach, watchdog restart after failed
validation, pre-release Hysteria pins) and keep every existing safety gate.

## Ownership

- Rotation lane: `ansible/roles/monitoring/templates/logrotate-xray.j2`,
  `tests/unit/test_monitoring_logrotate.py`, monitoring role notes.
- Resolver lane: `ansible/roles/amneziawg/tasks/enable.yml`,
  `ansible/roles/amneziawg/molecule/default/prepare.yml`, AWG role notes.
- Firewall lane: `ansible/roles/firewall/defaults/main.yml`,
  `ansible/roles/firewall/templates/nftables.conf.j2`, firewall tests and notes.
- Watchdog lane: `ansible/roles/watchdog/templates/vpn-watchdog.sh.j2`,
  watchdog tests and notes.
- Hysteria lane: `ansible/roles/hysteria/tasks/enable.yml`, its regression
  and notes.
- Primary owns snapshots, planning, task and board writes, review and commits.

## Execution

- [ ] ANS-1792500035125072 Guard Xray log rotation with the transport egress predicate and every-profile regressions #bug !high @item:ANS-1792499727513191
- [ ] ANS-1792500035840245 Remove the resolvconf install from AmneziaWG with package regressions #bug !high @item:ANS-1792499727513191
- [ ] ANS-1792500036500839 Drop AWG forwarding to canonical private destinations with policy equality regressions #bug !high @item:ANS-1792499727513191
- [ ] ANS-1792500037164561 Withhold watchdog recovery after failed configuration validation with state regressions #bug !high @item:ANS-1792499727513191
- [ ] ANS-1792500037843465 Require exact stable Hysteria version pins with pre-flight regressions #bug !high @item:ANS-1792499727513191
- [ ] ANS-1792500038523299 Pass focused and complete local checks plus independent review #bug !high @item:ANS-1792499727513191

## Verification

- Local: each new regression fails on the parent commit and passes after the
  fix; focused pytest files, `make snapshot-check`, `make molecule-test
  ROLE=amneziawg` where Docker allows, `./taskctl validate`, and `make check`.
- Remote CI: not requested in this change; a later PR records it.
- Dry-run/staging/live: not applicable; this change authorizes no deployment.
