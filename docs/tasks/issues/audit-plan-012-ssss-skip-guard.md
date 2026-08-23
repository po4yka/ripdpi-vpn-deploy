---
id: TST-1787495860092796
title: Skip age-recovery roundtrip when ssss-combine is absent
kind: bug
status: backlog
area: testing
priority: medium
risk: standard
owner: unassigned
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-23
spec_reason: test-only
related_tasks: []
---

## Goal

`tests/bats/age_recovery_roundtrip.bats` skips cleanly with an actionable message when `ssss-combine` is absent (fresh macOS), while CI (which installs ssss) still runs it for real.

Execution plan: `plans/012-age-recovery-ssss-skip.md`.

## Acceptance criteria

- Simulated absence (restricted PATH): all tests skipped, exit 0.
- Tools present: all tests pass.
- `bats tests/bats/` fully green; only the setup() function changed.

