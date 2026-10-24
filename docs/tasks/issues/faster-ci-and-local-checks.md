---
id: CIC-1792830107469586
title: Shorten CI and local check wall time
kind: chore
status: doing
area: ci
priority: high
risk: standard
owner: Claude
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-24
updated: 2026-10-24
spec_reason: tooling-only
related_tasks: []
---

## Goal

Cut the CI critical path and the local `make check` time without removing coverage: parallel native lanes, parallel pytest workers, fresher shard balancing, fewer duplicated runs and checks.

## Acceptance criteria

- Split the serial native runtime step into parallel CI jobs and run transport runtime acceptance in three groups; every native case still runs once with selected skips fatal.
- Run portable pytest with parallel workers locally and in each CI group, keeping complete disjoint shard coverage.
- Refresh the committed pytest duration profile from a verified CI artifact.
- Let a main push reuse a successful full-plan PR run for the identical tree; any uncertainty keeps full CI.
- Select native lanes for a `tests/unit/` change only when the changed file contains native tests.
- Remove duplicated work from `make check` and let its independent parts run under `make -j`.
- Drop the Intel macOS vpnd runners and share one restic repository build across restore completeness cases.
- Observe hosted CI passing on the PR and compare wall time with the 61-minute median baseline.
