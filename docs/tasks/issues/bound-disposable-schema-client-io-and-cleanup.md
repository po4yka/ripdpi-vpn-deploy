---
id: SCR-1791922948501055
title: Bound disposable schema client I/O and cleanup
kind: bug
status: review
area: scripts
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-14
updated: 2026-10-14
spec_reason: regression-tested-single-module
related_tasks: [MON-1791918647679583]
status_detail: 46 complete regression tests and independent source review passed. Full pinned local and exact-source hosted gates remain required before handoff; uncertain cleanup fails closed.
---

## Goal

Keep the disposable schema client within its existing input deadline and report confirmed cleanup only after client shutdown and successful removal of its owned container. Uncertain shutdown still permits a bounded removal attempt but requires status `125`. This repairs the local gate without changing provider, fleet or notification behavior.

## Acceptance criteria

- Nonblocking tar delivery preserves partial writes and retries transient backpressure inside the configured deadline.
- Cleanup attempts client shutdown before container removal; successful cleanup requires both. The existing 5/15/10-second bounds remain intact, and uncertain signaling, shutdown or removal requires status `125`.
- Executable regressions cover input stalls, data integrity, late creation and cleanup refusal. The timeout fixture controls client readiness without changing the production deadline.
- The complete local gate, independent review and exact-source hosted checks pass before handoff.
- No real Docker operations in regression probes, deployment, fleet operations or real Telegram messages.
