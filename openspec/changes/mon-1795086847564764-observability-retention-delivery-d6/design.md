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
