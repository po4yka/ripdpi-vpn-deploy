---
id: VPD-1787497584287174
title: Fix update-check version comparison and add network timeout
kind: bug
status: backlog
area: vpnd
priority: medium
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-23
spec_reason: regression-tested-single-module
related_tasks: []
---

## Goal

The update notice fires exactly when a genuinely newer vpnd release exists and never recommends a downgrade; the network check cannot hang the CLI.

## Audit evidence

| Finding | Evidence |
|---|---|
| String inequality instead of version compare; vpnd-v prefix filter vs repo-wide releases/latest | update.rs:9-10,88-101; two release trains (.github/workflows/release-please.yml and release-vpnd.yml vpnd-v*) |
| Blocking ureq call with no timeout inside async run | update.rs:45-86; comment claims "never block the caller on failure" but only covers Err |

## Acceptance criteria

- Version comparison understands ordering (locally newer than latest produces no notice; older produces one).
- Tag-scheme mismatch between release trains cannot suppress a newer vpnd-vX.Y.Z.
- A stalled connection fails within an explicit timeout and the command still exits 0 (check is advisory).
