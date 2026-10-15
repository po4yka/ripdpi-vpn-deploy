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
updated: 2026-10-15
spec_reason: regression-tested-single-module
related_tasks: [MON-1791825755591250]
status_detail: Bounded service identity, full local gate, exact-source hosted checks and independent review passed at f03923dfca69c3fa229444747bbe6939a21b7a41; deployment and real notifications remain excluded.
closed_at: "2026-10-15T16:25:34Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Source rendering acceptance retained from f03923dfca69c3fa229444747bbe6939a21b7a41 full local gate. Integrated source 923304729f6bdd32edce6a9b6ceada1d51c7d011 passed CI 38759230876 including native webhook timeout and complete 7193-case portable suite; current schema and Telegram portable tests passed 116 cases. No real notification or deployment claimed.
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
