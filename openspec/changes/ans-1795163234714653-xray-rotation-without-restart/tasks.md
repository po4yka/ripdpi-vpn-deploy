# ANS-1795163234714653: Stop the daily Xray restart from log rotation and tighten Xray runtime settings

## Objective

Daily log rotation leaves the running Xray process in place on every profile. Sniffing is routing-only, the per-connection buffer override is gone, and the Xray unit carries the added sandbox options with a file limit below the host table.

## Ownership

`ansible/roles/monitoring/templates/logrotate-xray.j2`, `ansible/roles/xray/templates/config.json.j2`, `ansible/roles/xray/templates/xray.service.j2`, both role `CLAUDE.md` files, their goldens under `tests/snapshot/golden/`, `tests/unit/test_monitoring_logrotate.py`, `tests/unit/test_transport_service_sandbox.py`, `tests/unit/test_transport_logrotate_native.py`, `tests/native/transport_acceptance/test_rotation.py` and `tests/DESIGN-NOTES.md`. One writer lane.

## Execution

- [x] ANS-1795163509998271 Replace the Xray rotation restart with copytruncate and cover it with unit and native tests #bug !high @item:ANS-1795163234714653
- [x] ANS-1795163550770687 Set routeOnly sniffing, drop the bufferSize override and harden the Xray unit with tests and snapshots #bug !high @item:ANS-1795163234714653

## Verification

- Local: `make snapshot-check`, the matching `tests/unit` files, `make check`.
- Remote CI: the PR checks on the exact commit, including Molecule for both roles and the native rotation lanes, which do not run on the workstation.
- Dry-run and live: an operator deploy; acceptance is that the Xray `ActiveEnterTimestamp` does not move across the next daily rotation and a rotated log copy exists.
- Staging, client and artifact: not applicable; no client payload or release artifact changes.
