---
id: CIC-1788690361800575
title: Bound CI runtime and cancel superseded auxiliary PR checks
kind: chore
status: done
area: ci
priority: high
risk: standard
owner: Codex
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-09-06
updated: 2026-09-06
spec_reason: tooling-only
related_tasks: []
status_detail: Protected main 0469ddabee7d25bf8c00ae5abafc7510f17d70e0 passed all 75 CI jobs; both old helper runs cancelled and newer runs succeeded.
closed_at: "2026-09-06T11:05:39Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Protected main 0469ddabee7d25bf8c00ae5abafc7510f17d70e0 passed all 75 CI jobs and CodeQL; all 35 concrete job templates bounded; both superseded helper executions cancelled and newer executions succeeded; local workflow, regression and hook checks passed.
---

## Goal

Bound every concrete job in the standard CI graph and auxiliary PR checks,
and cancel superseded auxiliary runs of the same PR.

## Acceptance criteria

- Every concrete job in ci.yml, its reusable callees and auxiliary PR checks
  has an explicit positive runtime limit; existing limits remain intact.
- CLAUDE coverage and Markdown link checks cancel older runs of the same PR;
  workflow names and PR identities isolate unrelated work, and scheduled link
  checks use unique groups.
- Existing CI/CodeQL cancellation and required status names remain intact.
  Reusable checks inherit parent CI cancellation without colliding with callers;
  release/deploy/cleanup cancellation is unchanged.
- Limits have headroom over observed runtimes. The shared Rust build limit also
  covers cold release/cross builds, without adding build cancellation.
- Actionlint, strict zizmor, relevant regression checks and protected PR/main CI
  pass; observe supersession outcomes without artificial delays or test workloads.
