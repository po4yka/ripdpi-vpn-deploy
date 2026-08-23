---
id: VPD-1787497584598165
title: Move blocking IO out of async contexts in vpnd
kind: chore
status: backlog
area: vpnd
priority: low
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-23
spec_reason: mechanical-refactor
related_tasks: []
---

## Goal

Blocking work leaves tokio worker threads: the pointless `id -u` subprocess is replaced, and heavy file operations move under spawn_blocking or shrink to negligible size.

## Audit evidence

| Finding | Evidence |
|---|---|
| `id -u` spawned via std::process on async paths (twice) | secrets.rs:84-92 (via share.rs:72); probe_matrix.rs:330-338 |
| std::fs bulk IO in async fns | ai_docs.rs bulk doc copy; probe_matrix.rs:784-792 report write; share.rs fs ops; doctor.rs:135-152 in-memory gzip |

## Acceptance criteria

- No std::process spawn on async paths; uid resolved once per process without a subprocess where feasible, or wrapped in spawn_blocking.
- Bulk IO sites (ai-docs emit, report write, bundle gzip) wrapped in spawn_blocking.
- cargo clippy -D warnings stays green; no behavior change.
