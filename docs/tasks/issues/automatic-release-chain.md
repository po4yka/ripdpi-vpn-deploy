---
id: CIC-1788652007140605
title: Close automatic vpnd release handoff
kind: bug
status: doing
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
---

## Goal

Enable release-please on main and explicitly hand newly created vpnd releases to the existing binary publication workflow on their verified tag revision.

## Acceptance criteria

- Release-please runs without a required opt-in variable and fails on errors.
- Only a newly created root release dispatches publication, using the validated tag and SHA.
- Wrong or missing tags, missing SHA, and dispatch failures cannot report success.
- Existing manual/tag publication and Cargo SBOM remain intact; delivery uses protected main and observed CI.
- Actual release publication requires a reviewed release PR merge and is not simulated as live evidence.
