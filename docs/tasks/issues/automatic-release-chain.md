---
id: CIC-1788652007140605
title: Close automatic vpnd release handoff
kind: bug
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
status_detail: Protected main ea94beef passed exact-main CI 34024059323 and release-please 34024059176; no root release was created, so publication dispatch correctly remained skipped.
closed_at: "2026-09-06T10:20:43Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Protected main ea94beef; exact-main CI 34024059323 and release-please 34024059176 succeeded; non-release dispatch correctly skipped.
---

## Goal

Enable release-please on main and explicitly hand newly created vpnd releases to the existing binary publication workflow on their verified tag revision.

## Acceptance criteria

- Release-please runs without a required opt-in variable and fails on errors.
- Generated release PRs clearly report the required native-workflow approval; CI and CodeQL must pass before the operator merges.
- Only a newly created root release dispatches publication, using the validated tag and SHA.
- Wrong or missing tags, missing SHA, and dispatch failures cannot report success.
- Existing manual/tag publication and Cargo SBOM remain intact; delivery uses protected main and observed CI.
- Actual release publication requires a reviewed release PR merge and is not simulated as live evidence.
