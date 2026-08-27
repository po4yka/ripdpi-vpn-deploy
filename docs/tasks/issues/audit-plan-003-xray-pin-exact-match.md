---
id: SCR-1787495848362337
title: Match pinned Xray version exactly in probe-matrix-driver
kind: bug
status: doing
area: scripts
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

`probe-matrix-driver.py` compares the installed Xray version token exactly against the pin, so a stale prefix pin (`v26.3.2` vs installed `v26.3.27`) yields the `version-mismatch` verdict instead of silently passing.

Execution plan: `plans/003-xray-pin-exact-match.md`.

## Acceptance criteria

- No substring containment against the version banner remains in the driver.
- Unit cases cover: exact match passes; prefix pin fails with `version-mismatch`; absent token fails; non-zero returncode fails.
- Full unit suite passes.
