## Context

Existing limits: collector `MemoryMax`, finite collector retention and a pinned vmagent queue (resource-bounded-observability). Drill tooling exists in `scripts/observability-operator.py`.

## Goals / Non-Goals

- One contract for retention and a proven delivery path.
- Non-goal: changing existing resource limits, message rendering, or Telegram relay behaviour.

## Decisions

- Retention table as a documented reference whose values are read by a unit test from the rendered templates. Rejected: a separate dashboard.
- Assumption: field-report aggregates inherit Prometheus retention and no new store exists (D2).
- Assumption: the delivery drill is a staging operation and needs operator authorization at run time; planning here does not authorize it.

## Contracts and ownership

- `docs/reference/observability-operations.md`, observability role templates, `contract/observability-evidence.schema.json`, `tests/unit/` retention test. The alert template is not edited here.

## Risks / Trade-offs

- Retention shortened below incident needs -> values are role variables with documented defaults.
- Receipt leaks identifiers -> receipt schema forbids token and chat id.

## Migration Plan

Forward only. Rollback reverts the table and flags. The delivery drill sends one test message.

## Implementation notes

- Every data class already had a finite bound in the rendered configuration; no retention flag was missing. The journald values moved from literals in the monitoring task to `monitoring.journald_system_max_use` and `monitoring.journald_max_retention` with the same defaults, so every row of the table is a role variable or a pinned template value.
- The receipt is the `deliveryReceipt` definition in `contract/observability-evidence.schema.json`. `observability-operator.py drill --receipt PATH` (Make: `OBSERVABILITY_DRILL_RECEIPT`) writes it only after the existing exact-nonce relay receipt is proven, from the Telegram message id that the relay reports.
- Dependency: the relay (`observability-telegram-relay.py`, owned by `MON-1794126016474351`) does not yet return the Telegram message id in its drill receipt, although it already reads it from the Bot API reply. Until that change lands, `--receipt` refuses with "delivery receipt lacks a Telegram message id" and the drill itself keeps its current result. This change does not edit the relay.
- Field-report raw retention is `none` by contract; no ingest exists yet, so the listing scenario of REQ-RET-FIELDREPORT is proven by the D2 ingest tests when D2 lands.
