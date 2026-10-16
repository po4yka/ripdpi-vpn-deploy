---
id: ANS-1791996724624876
title: Roll back private gateway runtimes with the frontend runtime
kind: bug
status: blocked
area: ansible
priority: medium
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1791996724624876-gateway-runtime-rollback
created: 2026-10-14
updated: 2026-10-16
related_tasks: []
status_detail: Native first-adoption interruption selection remains unresolved at source 087658e8. Authenticated GitHub API/Git SSH and Terraform registry connections time out; restore connectivity to publish diagnostics and finish native/full-gate acceptance.
---

## Goal

`make rollback-xray` moves every process that executes the pinned Xray release, not only `xray.service`. Today `transport_runtime_rollback.py` builds candidates for `xray.service` only, while `ripdpi-transport-direct.service` and `ripdpi-transport-warp.service` (`ansible/roles/transport-egress/templates/gateway.service.j2` ExecStart, bound to `xray_runtime_binary` in `transport-egress/tasks/stage.yml`) keep running the release being rolled back, and acceptance checks only frontend units. Adding gateway units to the rollback candidates directly would create a second writer for egress-owned files and wedge the next deploy with `accepted-authority-changed` (every applied candidate becomes a permanent node in the runtime receipt). The fix needs a single-owner decision: every file whose content binds the pinned release path is published by the runtime plan in every flow, and the owned gateway set comes from `/etc/ripdpi/transport-egress/generation.json` `gateway_units`, not a duplicated constant. Found by the 2026-10-14 deep audit (H3 residual); `docs/RUNBOOK-rollback.md` documents the interim limitation.

## Acceptance criteria

- After a runtime rollback, the frontend and both private gateway main processes execute the rolled-back release (native `/proc/<MainPID>/exe` proof), and a following ordinary deploy with the newer pin succeeds.
- Interrupted or refused rollback restores the complete previous generation for all three units.
- No file is published by two owners; portable tests pin the ownership boundary.
