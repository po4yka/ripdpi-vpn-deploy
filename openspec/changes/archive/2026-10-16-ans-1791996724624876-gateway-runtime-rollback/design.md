## Context

See `proposal.md`. `ansible/roles/runtime-release/files/transport_runtime_rollback.py` builds rollback candidates for `xray.service`, its links and assets only. `ansible/roles/transport-egress/tasks/stage.yml` publishes `ripdpi-transport-direct.service` and `ripdpi-transport-warp.service` from `gateway.service.j2`, whose ExecStart is `xray_runtime_binary`. The runtime transaction records every applied candidate as a permanent node of its accepted receipt and `Transaction.accepted()` refuses `accepted-authority-changed` when a claimed node's identity differs, so a second writer for the gateway units wedges the next deploy.

## Goals / Non-Goals

- Goal: one owner publishes every unit file that binds the pinned Xray release path, in deploy, upgrade and rollback.
- Goal: rollback moves the frontend and both private gateways together and proves each executable.
- Non-goal: changing gateway routing, credentials or the egress generation contract.

## Decisions

- The runtime plan becomes the single publisher of the gateway unit files: `stage.yml` stops publishing them directly and appends them to the runtime candidates; egress keeps ownership of gateway lifecycle and generation state. Hysteria isolated candidate admission receives the selected gateway executable from the runtime plan instead of requiring a published gateway unit. Rejected: adding gateway units to rollback candidates while egress still publishes them (two writers, wedges the next deploy).
- The owned gateway set is read from `/etc/ripdpi/transport-egress/generation.json` `gateway_units`, validated by the existing generation reader. Rejected: a duplicated constant plus unit-file existence checks.
- Executable proof for gateways lives in the rollback/egress acceptance path, not in the shared `Adapter.ready()` used by upgrade, refresh, retirement and adoption.

## Contracts and ownership

- Runtime publisher: owns every unit file binding the release path. Egress: owns gateway lifecycle and generation records.

## Risks / Trade-offs

- Changing the gateway unit publisher touches every deploy. Mitigation: native acceptance for deploy, upgrade, rollback and an ordinary converge after rollback.

## Migration Plan

Existing nodes adopt the gateway unit files into the runtime receipt on the next deploy through the existing adoption path. Operator rollback refuses missing gateway claims before publication, so adoption must complete first. Runtime release rollback remains supported within this publisher contract. Returning to the older egress publisher after adoption is a separate state migration: a source-only revert and redeploy can invalidate accepted inode claims. Recreate the disposable node from the selected source or restore a complete previously accepted generation through a separately authorized recovery; do not alternate publishers against the same receipt. No compatibility writer or automatic claim deletion is added.
