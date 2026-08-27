---
id: MON-1787495848936301
title: Bound external curls with connect and max timeouts
kind: bug
status: review
area: monitoring
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-27
spec_reason: regression-tested-single-module
related_tasks: []
status_detail: Implementation and targeted regressions passed; exact-source hosted CI and final closure remain pending.
---

## Goal

Every external curl in the cron-path scripts (check-host.net, ntfy pushes, binary downloads) carries `--connect-timeout` and `--max-time`, so a stalled connection degrades to the existing failure/retry path instead of hanging cron runs indefinitely.

Execution plan: `plans/007-curl-timeouts-cron-paths.md`.

## Acceptance criteria

- Enumeration grep shows zero unbounded external curls in the eight listed scripts.
- Existing `|| echo ... failed` continuations after ntfy pushes intact.
- `bash -n` clean on all touched files; `make shellcheck` exit 0.
