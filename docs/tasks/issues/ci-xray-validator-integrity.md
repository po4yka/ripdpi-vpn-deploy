---
id: CIC-1788668056138767
title: Verify shared Xray CI validator integrity
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
status_detail: Protected main ea94beef passed both shared Xray validator consumers, molecule xray, both full-stack scenarios and required checks in exact-main CI 34024059323.
closed_at: "2026-09-06T10:20:44Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Protected main ea94beef; exact-main CI 34024059323 passed both Xray validator consumers, Xray Molecule, full-stack and required checks.
---

## Goal

Both Xray CI validator jobs must verify the same reviewed archive digest before
extracting or executing the runtime.

## Acceptance criteria

- Template and sentinel validation share one version/hash pin and installer.
- The pin matches the example configuration; drift fails before download.
- Corrupt archives and failed downloads cannot execute or install a runtime.
- Targeted executable regressions and both hosted validator jobs pass.
- Deliver the change through protected main and observe exact-commit CI.
