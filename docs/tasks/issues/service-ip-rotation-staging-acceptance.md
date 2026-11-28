---
id: OPS-1795867688528839
title: Accept service IPv4 rotation on a disposable staging node with a refreshed client
kind: chore
status: backlog
area: operations
priority: medium
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ops-1795867688528839-service-ip-rotation-staging-acceptance
created: 2026-11-28
updated: 2026-11-28
related_tasks: [OPS-1795856574795376]
---

## Goal

One disposable staging node completes the full service IPv4 rotation cycle from `docs/how-to/rotate-service-ip.md` with a real client device: attach a new generation, move DNS, refresh the device, retire the old generation. This owns the dry-run, staging and client evidence that `OPS-1795856574795376` transferred when its source change closed.

## Acceptance criteria

- `make dry-run` on the staging node after the first attach shows the service address unit and no server replacement (dry-run evidence).
- Plan, apply, inventory and deploy attach the new generation; the guest owns its `/32`; `make verify` and `make burn-check` pass on the new client address; the plan that retires the old generation deletes only its address resource (staging evidence).
- A real device refreshed through its unchanged subscription URL passes authenticated traffic on the new address, and its SSH and Tailnet management path stays on the primary address (client evidence).
- The disposable node and its addresses are retired afterwards through the cleanup workflow.
