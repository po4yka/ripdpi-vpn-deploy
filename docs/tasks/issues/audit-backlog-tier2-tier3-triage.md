---
id: OPS-1787495860232652
title: Triage tier-2 and tier-3 findings from 2026-08-23 plumbing audit
kind: research
status: backlog
area: operations
priority: low
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-23
spec_reason: research-only
related_tasks: []
---

## Goal

Remaining findings from the 2026-08-23 deep audit of scripts/tests/tasking are triaged into planned work or explicit rejections, so no audit finding is lost. Tier-2 candidates: decrypt-secrets.sh zero coverage; blue-green/fleet-rotate happy-path tests; taskctl negative-path test harness; shellcheck gate for root-side .j2 templates; UTF-8 encoding sweep (~40 sites); local validate without terraform init; exception-root local validation; galaxy collections local install; tool-pinning consistency; check-prereqs expansion; ci-fast parallelization. Full list: `plans/README.md` (rejected/deferred section).

Execution: no handoff plan yet — produce plans for the selected tier-2 batch after maintainer prioritization.

## Acceptance criteria

- Every tier-2 finding has either a handoff plan under `plans/` or an explicit rejection rationale in `plans/README.md`.
- Tier-3 polish items are either folded into tier-2 plans or explicitly rejected with rationale.
- Decision summary recorded in this task's execution record before any implementation starts.

