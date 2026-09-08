---
id: VPD-1787497584429255
title: Make host registry persistence atomic
kind: bug
status: done
area: vpnd
priority: medium
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-09-08
spec_reason: regression-tested-single-module
related_tasks: []
closed_at: "2026-09-08T16:59:15Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Atomic temp+rename registry persistence with exclusive 0600 temp files merged as c82a41c1b8784b01f58ff57ea035ef6e9f7904d0 via PR #205; registry_roundtrip.rs covers concurrent writers, torn-read readers, mode 0600, corrupt-file load errors and temp-file cleanup. Exact-main ci run 34249394952 and codeql run 34249394663 green."
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
