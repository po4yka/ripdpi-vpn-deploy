---
id: TST-1787495848194568
title: Make snapshot-update fail loudly on render errors
kind: bug
status: doing
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
---

## Goal

`scripts/render-snapshots.py --update` reports templates that failed to render on stderr and exits 1, while still writing goldens for templates that rendered successfully; the update path can no longer print a success message over hidden breakage.

Execution plan: `plans/002-snapshot-update-error-propagation.md`.

## Acceptance criteria

- A broken template plus `--update` exits non-zero and names the template (unit-proven).
- Valid goldens are still refreshed on the same run.
- Check-mode drift detection and clean-run exit 0 behavior unchanged (regression tests).
