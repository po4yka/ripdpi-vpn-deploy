---
id: MON-1787495859494660
title: Use portable millisecond clock in idle-cycle-measure
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
status_detail: Implementation and targeted regressions passed; final source CI and closure lifecycle remain pending.
---

## Goal

`idle-cycle-measure.sh` produces millisecond timestamps via a portable helper instead of GNU-only `date +%s%3N`, so the measurement cycle works on BSD/macOS vantage boxes instead of dying at the first cold probe.

Execution plan: `plans/008-portable-ms-timestamps.md`.

## Acceptance criteria

- No `%3N` remains in the script; `now_ms` helper defined once.
- `--argjson` arithmetic proof emits valid JSON with positive elapsed.
- `bash -n` + `make shellcheck` clean.
