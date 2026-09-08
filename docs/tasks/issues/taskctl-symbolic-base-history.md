---
id: CIC-1788896215087324
title: Resolve symbolic base refs in deleted task history validation
kind: bug
status: review
area: ci
priority: medium
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-09-08
updated: 2026-09-08
spec_reason: regression-tested-single-module
related_tasks: []
status_detail: Symbolic base refs now resolve to commit SHAs before deleted-history indexing; focused regression and full taskctl tests pass, and the real committed purge validates against origin/main.
---

## Goal

Make base-aware task validation accept any Git revision expression that resolves
to the selected baseline commit, including the documented `origin/main` form,
when validating committed task deletion history.

## Acceptance criteria

- `./taskctl validate --base origin/main` validates a committed OpenSpec task
  purge without raising an internal `KeyError`.
- Historical evidence validation uses the resolved baseline commit consistently
  while preserving the original ancestry and fail-closed lifecycle checks.
- A regression test covers a symbolic base ref through the public validation
  command, and the focused taskctl suite plus repository task gates pass.
