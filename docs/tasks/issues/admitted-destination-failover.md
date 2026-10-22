---
id: SEC-1792678909985498
title: Fail over TCP connections across admitted destination addresses
kind: feature
status: doing
area: security
priority: high
risk: high
owner: transport-audit
parent: null
blocked_by: []
spec_mode: required
openspec_change: admitted-destination-failover
created: 2026-10-22
updated: 2026-10-22
related_tasks: []
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
