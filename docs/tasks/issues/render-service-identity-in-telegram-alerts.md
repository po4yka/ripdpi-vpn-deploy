---
id: MON-1791918647679583
title: Render service identity in Telegram alerts
kind: bug
status: done
area: monitoring
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-13
updated: 2026-10-16
spec_reason: regression-tested-single-module
related_tasks: [MON-1791825755591250]
status_detail: Integrated main source 3010dfb517b84cd7fbe9c3512b30b87d63b64fe8 passed all 88 source/native CI jobs in 38792726270 and both CodeQL analyses; focused local evidence and the unsuccessful monolithic local attempt are recorded. No external rollout or real notification receipt claimed.
closed_at: "2026-10-15T20:06:17Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Service identity rendering and failure boundaries pass focused tests and complete source/native CI 38792726270 on integrated main 3010dfb517b84cd7fbe9c3512b30b87d63b64fe8. Actual isolated relay and monitoring acceptance passed; no real Telegram or human receipt claimed.
---

## Goal

Identify each failed or missing required service in its bounded Telegram alert line, including recovery, when multiple services share one node and notification group.

This follows the archived alerting repair: per-unit rules retain `role`, but the relay omitted it and produced indistinguishable lines. The terminal record remains intact; this record owns the newly identified rendering regression.

## Acceptance criteria

- Actual rendered required-service rules produce distinct firing and recovery lines for two roles on the same node.
- Service alerts require a technical role of at most 64 characters; malformed or missing identity is refused categorically.
- Unrelated alerts may omit role. Grouping, notification frequency, escaping, redaction and message omission bounds remain intact.
- Regression tests, complete local checks, independent review and exact-source hosted checks pass before review completion.
- No deployment or real Telegram message; source proof remains separate from live and human acceptance.
