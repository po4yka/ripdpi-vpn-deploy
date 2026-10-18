# OPS-1792305989358872: Repair recovery and delivery boundaries

## Objective

Fix all eight repeated-audit defects, prove their failure boundaries with
regressions, pass required source checks and merge reviewed source without deployment.

## Ownership

- Recovery worker: scripts/terraform-env.sh, scripts/blue-green.sh,
  scripts/new-cohort.sh, scripts/backup-tf-state.sh, the state restore helper,
  scripts/restore.sh, scripts/CLAUDE.md, docs/RUNBOOK-incident.md,
  docs/RUNBOOK-restore.md and their dedicated unit/Bats tests.
- Delivery worker: ansible/roles/subscription-host/, scripts/client_payload.py,
  tests/unit/test_recipient_port_hopping.py,
  tests/unit/test_subscription_share_permissions.py and
  tests/unit/test_subscription_mirror_lifecycle.py.
- Network worker: ansible/roles/firewall/, tests/unit/test_firewall_dhcpv6.py,
  tests/native/transport_acceptance/test_dhcpv6.py and its minimal runner registration.
- Integration owner: ansible/roles/backup/, matching backup tests,
  tests/CLAUDE.md, snapshot refresh, task/spec files and all Git operations.
- Shared-file changes and commits are serialized by the integration owner.
  Workers retain other agents' changes and do not stage or commit files.

## Execution

- [x] OPS-1792306162286391 Refuse reserved environment aliases before provisioning #bug !high @item:OPS-1792305989358872
- [x] OPS-1792306163221571 Publish and restore Terraform state atomically #bug !high @item:OPS-1792305989358872
- [ ] OPS-1792306164184160 Protect published share bundle read permissions #bug !high @item:OPS-1792305989358872
- [x] OPS-1792306165929686 Refuse unsupported RIPDPI Hysteria port hopping #bug !high @item:OPS-1792305989358872
- [x] OPS-1792306167846329 Verify complete effective-profile restore artifacts #bug !high @item:OPS-1792305989358872
- [ ] OPS-1792306168913886 Retire disabled mirror execution without losing authority #bug !high @item:OPS-1792305989358872
- [x] OPS-1792306169855109 Repair complete disaster recovery procedures #bug !high @item:OPS-1792305989358872
- [ ] OPS-1792306170781535 Admit scoped DHCPv6 bootstrap and rebind traffic #bug !high @item:OPS-1792305989358872
- [ ] OPS-1792306171697997 Run integration security and CI gates and land reviewed source #bug !high @item:OPS-1792305989358872

## Verification

- Local: focused pytest and Bats failure tests, role parser/lint checks,
  reviewed snapshot updates, make check and clean task contracts.
- Remote CI: exact source SHA required checks, affected real Molecule roles
  and complete selected native suites including DHCPv6 packet admission.
- Dry-run: synthetic recovery/check-mode tests only; no real host check mode.
- Artifact: exact source diff, snapshots, private-mode and cleanup assertions.
- Staging/live/client deployment: not applicable; the user prohibits deployment.
