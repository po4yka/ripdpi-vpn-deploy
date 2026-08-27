---
id: MON-1787495859494660
title: Use portable millisecond clock in idle-cycle-measure
kind: bug
status: done
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
closed_at: "2026-08-27T14:12:47Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Portable millisecond clock regression uses the Python nanosecond clock and does not require GNU date. Implementation verified at 1221ccb59ae90f4d5d7fc3951018dcbef1634841: local make check passed (1055 pytest, one pre-existing network-scan skip, 55 Bats, 79 Terraform tests, 45 Conftest tests, 102 snapshots); hosted CI run 33079404315 passed all 51 jobs. Probe schema synchronization is a separate withheld task."
---

## Goal

`idle-cycle-measure.sh` produces millisecond timestamps via a portable helper instead of GNU-only `date +%s%3N`, so the measurement cycle works on BSD/macOS vantage boxes instead of dying at the first cold probe.

Execution plan: `plans/008-portable-ms-timestamps.md`.

## Acceptance criteria

- No `%3N` remains in the script; `now_ms` helper defined once.
- `--argjson` arithmetic proof emits valid JSON with positive elapsed.
- `bash -n` + `make shellcheck` clean.
