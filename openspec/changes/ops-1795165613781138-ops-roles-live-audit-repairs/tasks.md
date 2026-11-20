# OPS-1795165613781138: Close operations-role gaps from the 2026-11-20 fleet audit

## Objective

Managed nodes hold the recovery, backup, patch-window and local-audit properties in `operations/ops-roles-audit-repairs`.

## Ownership

`ansible/roles/watchdog/`, `ansible/roles/backup/`, `ansible/roles/package_updates/`, `ansible/roles/tailnet-management/`, `ansible/roles/security_audit/`, `ansible/roles/runtime-release/`, the restore-drill default in `ansible/roles/observability_agent/defaults/main.yml`, the `enable_watchdog` line of `ansible/group_vars/vpn-p1-web.yml` and `ansible/group_vars/vpn-p2-udp.yml`, `scripts/fleet_inspection.py`, and the tests, snapshots and documents that state these contracts. One writer; no shared-file lane.

## Execution

- [x] OPS-1795165849317051 Make the watchdog safe for single-transport nodes and enable it for vpn-p1-web and vpn-p2-udp #bug !high @item:OPS-1795165613781138
- [x] OPS-1795165951713970 Add backup start deadlines and refuse a sync onto a different remote repository #bug !high @item:OPS-1795165613781138
- [x] OPS-1795166046539242 Run the restore drill weekly and align the inspection and adapter freshness windows #bug !high @item:OPS-1795165613781138
- [x] OPS-1795166130277066 Report a pending reboot in passive inspection and stagger the unattended-upgrade hour #bug !high @item:OPS-1795165613781138
- [x] OPS-1795166204645783 Disable tailscaled log upload, the Lynis online version test and the unbounded activation lock wait #bug !high @item:OPS-1795165613781138
- [x] OPS-1795166270610878 Run the narrow checks, refresh snapshots and record evidence in verification.md #bug !high @item:OPS-1795165613781138

## Verification

Local: the matching `tests/unit` files, `make snapshot-check`, `make task-check`, `make validate`, and Molecule for the changed roles where Docker can run the pinned images. Remote CI: the pull request checks, which run the Molecule scenarios and the Linux-only tests. Dry run and live: `make dry-run` and deployment for each node under separate operator authorization, after the probe identities exist in the encrypted secrets. Staging, client and artifact gates do not apply.
