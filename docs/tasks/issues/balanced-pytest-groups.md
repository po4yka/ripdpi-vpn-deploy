---
id: CIC-1788672821616865
title: Balance portable pytest across four CI groups
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
status_detail: Protected main ea94beef passed all four pytest groups and required aggregate in exact-main CI 34024059323; observed group wall times were 6m02s, 6m01s, 4m47s and 5m44s.
closed_at: "2026-09-06T10:20:43Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Protected main ea94beef; exact-main CI 34024059323 passed four pytest groups and required aggregate; full local make check passed.
---

## Goal

Run the portable pytest suite in four measured, balanced CI groups while retaining the existing required status and full test coverage.

## Acceptance criteria

- Preserve all portable tests from both test directories and the separate native lane.
- Use recorded Linux durations to balance four groups; retain a repeatable profile refresh.
- Reject missing, overlapping or incomplete shard results and selected test skips.
- Preserve the required `pytest unit tests` check without changing branch protection.
- Observe all four groups and aggregate CI passing, compare runtime with the serial baseline, and deliver to protected main.
