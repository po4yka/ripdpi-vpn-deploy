---
id: "SCR-1791617975137354"
title: "Make REALITY target validation bounded standards-correct and truthful"
kind: "bug"
status: "backlog"
area: "scripts"
priority: "medium"
risk: "high"
owner: "primary"
parent: "EPC-1791618453830051"
blocked_by: []
spec_mode: "required"
openspec_change: "reality-target-validation"
created: "2026-10-10"
updated: "2026-10-10"
related_tasks: ["SEC-1791545689674403", "ANS-1791586652330612"]
---

## Goal

Make REALITY target validation bounded standards-correct and truthful.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: A20; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
