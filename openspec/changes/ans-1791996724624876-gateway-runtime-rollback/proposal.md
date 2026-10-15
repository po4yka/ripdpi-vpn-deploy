# Change: Roll back private gateway runtimes with the frontend runtime

Task ID: `ANS-1791996724624876`

## Why

Operator runtime rollback (`make rollback-xray`) retargets only `xray.service`. The private gateways `ripdpi-transport-direct.service` and `ripdpi-transport-warp.service` execute the same pinned Xray release through egress-owned unit files, so after a rollback the egress leg of every proxied connection keeps running the release being rolled back, and acceptance reports success because it checks only frontend units. Adding the gateway units to the rollback candidates directly would give egress-owned files a second writer and wedge the next deploy with `accepted-authority-changed`. Found by the 2026-10-14 deep audit as the residual of H3; ANS-1791996027408136 documents the interim limitation.

## What Changes

- Every unit file that binds the pinned Xray release path is published by the runtime plan in every flow (deploy, upgrade, rollback), so rollback can move frontend and gateways together without a second owner.
- The owned gateway set is read from the egress generation record rather than a duplicated constant.
- Rollback acceptance proves the executable of every moved process and restores the complete previous generation on refusal or interruption.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `transports/runtime-acceptance-transaction`: operator runtime rollback covers every process that executes the pinned Xray release.

## Impact

- Ansible: `ansible/roles/transport-egress/tasks/stage.yml`, `ansible/roles/transport-egress/templates/gateway.service.j2`, `ansible/roles/runtime-release/files/transport_runtime_rollback.py`, `ansible/roles/runtime-release/files/transport_runtime_accept.py`.
- Tests: portable ownership and candidate tests, native rollback lane.
- Docs: `docs/RUNBOOK-rollback.md` (remove the interim limitation).
- Scope: source implementation and native validation; live deployment is outside scope.
