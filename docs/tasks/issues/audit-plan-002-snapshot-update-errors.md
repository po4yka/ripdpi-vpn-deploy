---
id: TST-1787495848194568
title: Make snapshot-update fail loudly on render errors
kind: bug
status: done
area: testing
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
closed_at: "2026-08-27T14:12:46Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Snapshot tests prove renderer failures are reported and fail the update instead of publishing incomplete goldens. Implementation verified at 1221ccb59ae90f4d5d7fc3951018dcbef1634841: local make check passed (1055 pytest, one pre-existing network-scan skip, 55 Bats, 79 Terraform tests, 45 Conftest tests, 102 snapshots); hosted CI run 33079404315 passed all 51 jobs. Probe schema synchronization is a separate withheld task."
---

## Goal

`scripts/render-snapshots.py --update` reports templates that failed to render on stderr and exits 1, while still writing goldens for templates that rendered successfully; the update path can no longer print a success message over hidden breakage.

Execution plan: `plans/002-snapshot-update-error-propagation.md`.

## Acceptance criteria

- A broken template plus `--update` exits non-zero and names the template (unit-proven).
- Valid goldens are still refreshed on the same run.
- Check-mode drift detection and clean-run exit 0 behavior unchanged (regression tests).
