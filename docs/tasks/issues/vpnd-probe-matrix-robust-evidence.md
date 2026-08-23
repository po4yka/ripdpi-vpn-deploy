---
id: VPD-1787497252303967
title: Fix probe-matrix process leaks, timeouts, durability, and evidence semantics
kind: bug
status: backlog
area: vpnd
priority: high
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: vpd-1787497252303967-vpnd-probe-matrix-robust-evidence
created: 2026-08-23
updated: 2026-08-23
related_tasks: []
---

## Goal

Probe-matrix runs are bounded and durable: timed-out cells die with their processes, the control probe cannot stall the run, interruptions preserve partial evidence with an honest exit code, zero durations are rejected, and impairment windows claim only filtering evidence.

## Audit evidence

| Finding | Evidence |
|---|---|
| Timed-out cells leak child processes (no kill_on_drop) | probe_matrix.rs:236-258 timeout drops the future; process.rs has no kill_on_drop anywhere |
| Control probe runs without timeout | probe_matrix.rs:226 awaited bare vs cells wrapped at :236 |
| Whole session in RAM, single terminal write; no signal handling | probe_matrix.rs:220-297; main.rs has no tokio::signal usage; one panicking task also kills the run via collect_ordered `?` at :300-307 |
| --duration 0 yields empty report exit 0 | parse_duration probe_matrix.rs:767-782 accepts 0; only interval validated at :208-210 |
| windows() conflates local failures with filtering | onset on any verdict != Ok incl Unknown/Error at probe_matrix.rs:576-585 |

## Acceptance criteria

- Timeout test proves no surviving child process after cancellation.
- Hanging control stub records Unknown and the run continues.
- Simulated interrupt leaves all observed ticks on disk marked interrupted with nonzero exit; duration 0 rejected at validation.
- Unknown-only series produces no window; Blocked→Ok recovery still detected; insta snapshot refreshed with schema_version bump documented in docs/PROBE-MATRIX.md.
