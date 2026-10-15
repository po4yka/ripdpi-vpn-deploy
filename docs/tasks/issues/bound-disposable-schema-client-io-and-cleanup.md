---
id: SCR-1791922948501055
title: Bound disposable schema client I/O and cleanup
kind: bug
status: done
area: scripts
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-14
updated: 2026-10-16
spec_reason: regression-tested-single-module
related_tasks: [MON-1791918647679583]
status_detail: Integrated main source 3010dfb517b84cd7fbe9c3512b30b87d63b64fe8 passed all 88 source/native CI jobs in 38792726270 and both CodeQL analyses; focused local evidence and the unsuccessful monolithic local attempt are recorded. No external rollout or real notification receipt claimed.
closed_at: "2026-10-15T20:06:17Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Integrated main source 3010dfb517b84cd7fbe9c3512b30b87d63b64fe8 passed all 88 CI jobs in 38792726270 and both CodeQL analyses. Full bounded-I/O cleanup regressions plus observed focused Mac coverage and unchanged hosted source gate satisfy approved source acceptance; monolithic local failure and queued cancellation remain recorded. No external infrastructure.
---

## Goal

Keep the disposable schema client within its existing input deadline and report confirmed cleanup only after client shutdown and successful removal of its owned container. Uncertain shutdown still permits a bounded removal attempt but requires status `125`. This repairs the local gate without changing provider, fleet or notification behavior.

## Acceptance criteria

- Nonblocking tar delivery preserves partial writes and retries transient backpressure inside the configured deadline.
- Cleanup attempts client shutdown before container removal; successful cleanup requires both. The existing 5/15/10-second bounds remain intact, and uncertain signaling, shutdown or removal requires status `125`.
- Executable regressions cover input stalls, data integrity, late creation and cleanup refusal. The timeout fixture controls client readiness without changing the production deadline.
- Focused Mac regressions, independent review, full-history/staged secret scanning and complete unchanged exact-SHA hosted source/native checks pass before handoff.
- No real Docker operations in regression probes, deployment, fleet operations or real Telegram messages.

## Source acceptance scope (2026-10-15)

The owner-approved source-only criteria require focused Mac regressions,
full-history/staged secret scanning and the complete unchanged exact-SHA hosted
source/native checks. The local monolithic attempt failed on a registry timeout;
its retry was cancelled while still queued behind the machine-wide build gate.
No full local success is claimed. Global and future deployment gates remain
unchanged.
