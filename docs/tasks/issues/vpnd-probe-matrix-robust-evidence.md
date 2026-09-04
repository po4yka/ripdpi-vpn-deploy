---
id: VPD-1787497252303967
title: Fix probe-matrix process leaks, timeouts, durability, and evidence semantics
kind: bug
status: review
area: vpnd
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: vpd-1787497252303967-vpnd-probe-matrix-robust-evidence
created: 2026-08-23
updated: 2026-09-01
related_tasks: []
status_detail: Probe durability, schema-3 producer, byte-identical client mirror, protected integration, and exact-main hosted checks are delivered. The task remains in review pending required staging and live four-protocol probe evidence; fixtures and source CI are not live acceptance.
---

## Goal

Probe-matrix runs are bounded and durable: timed-out cells die with their processes, the control probe cannot stall the run, interruptions preserve partial evidence with an honest exit code, zero durations are rejected, and impairment windows claim only filtering evidence.

## Audit evidence

| Finding | Evidence |
|---|---|
| Direct-child cancellation exists; descendant cleanup is unproven | Main 069f664 has kill_on_drop on run/capture, but no capture process group; a real Make child/grandchild timeout regression is required |
| Control timeout already exists; regression is missing | Main 069f664 run_control uses tokio::time::timeout and Unknown/control_timeout; add a real hanging-control regression without rewriting that behavior |
| Whole session in RAM, single terminal write; no signal handling | probe_matrix.rs:220-297; main.rs has no tokio::signal usage; one panicking task also kills the run via collect_ordered `?` at :300-307 |
| --duration 0 yields empty report exit 0 | parse_duration probe_matrix.rs:767-782 accepts 0; only interval validated at :208-210 |
| windows() conflates local failures with filtering | onset on any verdict != Ok incl Unknown/Error at probe_matrix.rs:576-585 |

## Acceptance criteria

- Timeout test proves no surviving child process after cancellation.
- Hanging control stub records Unknown and the run continues.
- Simulated interrupt leaves all observed ticks on disk marked interrupted with nonzero exit; duration 0 rejected at validation.
- Unknown-only series produces no window; Blocked→Ok recovery still detected; insta snapshot refreshed with schema_version bump documented in docs/PROBE-MATRIX.md.

## High-priority implementation ownership

- The vpnd subagent owns vpnd source/tests and docs/PROBE-MATRIX.md for share/probe-matrix hardening and audit coverage.
- The primary agent serializes task/OpenSpec records, generated board, Makefile, shared CI/toolchain files, documentation inventory, staging, commits, and remote delivery. Agents do not commit or mutate credentials/infrastructure.
- Worktree: `codex/complete-high-review`. All writers preserve unrelated changes and coordinate shared-file edits.

## Bounded runtime ownership — 2026-08-28

- The runtime agent owns the explicit capture policy/group guard, signal cancellation scoped to ProbeMatrix/Doctor dispatch, their opt-in call sites, probe duration/windows, existing relevant Rust tests/snapshot, the existing rustix process feature and this task's planning/evidence on `codex/high-probe-runtime-20260828` from `069f664949cd04ca3d64954b6135cf48258e443c`.
- This slice targets steps 1429/9177/2715025 without changing schema 2. Share/Reconverge keep foreground behavior and do not gain group cleanup. The durability step 2698055, schema-3/client synchronization, writer/journal handling, broad gates and host acceptance remain separate; this slice does not close the portfolio task.
