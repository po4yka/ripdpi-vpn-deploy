---
id: VPD-1787497584429255
title: Make host registry persistence atomic
kind: bug
status: backlog
area: vpnd
priority: medium
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-23
spec_reason: regression-tested-single-module
related_tasks: []
---

## Goal

Host registry writes survive crashes and concurrent invocations: temp+rename persistence matching the pattern share.rs and probe_matrix.rs already use.

## Audit evidence

| Finding | Evidence |
|---|---|
| save() truncates hosts.toml in place, no temp+rename, no lock | registry.rs:43-51; contrast write_private share.rs:181-193 and write_report probe_matrix.rs:784-792 |
| Registry drives reconverge targeting | commands/host.rs:10-41 load-modify-save cycle |

## Acceptance criteria

- Crash mid-write cannot lose existing records (temp+rename).
- Corrupt-file load error is covered by a test.
- Concurrent add operations serialize or last-write-wins atomically without torn files.
