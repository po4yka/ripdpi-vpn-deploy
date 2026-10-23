---
id: SEC-1792678909985498
title: Fail over TCP connections across admitted destination addresses
kind: feature
status: done
area: security
priority: high
risk: high
owner: transport-audit
parent: null
blocked_by: []
spec_mode: required
openspec_change: admitted-destination-failover
created: 2026-10-22
updated: 2026-10-23
related_tasks: []
closed_at: "2026-10-23T11:11:47Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Implemented admitted TCP destination failover with 88 real socket regression cases, immutable policy-admitted candidates, shared deadlines, bounded concurrency and no application replay. Source main 69bbf62f930de88a04106d43161dbc0dca511930 passed full local checks on its identical tree (10152 Python tests, 45 subtests, 387 vpnd tests and 10 docs tests), exact-head PR CI 39923816763 and exact-main CI 39934072990, including all seven native jobs and owned cleanup. Independent source review approved; archive Purpose warning reconciled in the canonical specification and strict validation passed. This completion covers the source helper capability, not a fleet rollout.
---

## Goal

Complete a TCP request through a later admitted destination address when an earlier DNS candidate stalls or fails, preserving isolation and never replaying application bytes.

## Acceptance criteria

- A real owned IPv6 destination completes after a stalled IPv4 candidate; a later A record completes after a refused earlier A record.
- One admitted DNS snapshot, per-candidate policy recheck, family ordering, eight-attempt/two-control limits and one connection deadline are enforced.
- Losing, failed, canceled and expired sockets close; worker and connection capacity return to idle.
- Pipelined application bytes reach only the committed winner; relay failure never retries or replays them.
- UDP single-literal and one-send behavior remains unchanged.
- Complete affected real-socket suites, strict task/OpenSpec validation, local `make check` and hosted CI pass on the reviewed implementation. Refusal-only behavior or test fixtures alone cannot close this feature; the real positive runtime path must be implemented.
