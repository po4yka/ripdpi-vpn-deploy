---
id: SCR-1791617975137354
title: Make REALITY target validation bounded standards-correct and truthful
kind: bug
status: done
area: scripts
priority: medium
risk: high
owner: primary
parent: EPC-1791618453830051
blocked_by: []
spec_mode: required
openspec_change: reality-target-validation
created: 2026-10-10
updated: 2026-10-16
related_tasks: [SEC-1791545689674403, ANS-1791586652330612]
status_detail: Implemented and validated exact source 4e043c0f; complete hosted CI 88 jobs, native REALITY 72 cases zero skips, affected portable suites 88 cases. Full local gate limitation recorded explicitly.
closed_at: "2026-10-16T12:52:19Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Implemented source 4e043c0f72345d3e3767415a56fead2391466913; full hosted CI 38895409950 passed all 88 jobs, CodeQL and dedicated native workflow 38895410063 passed; 72 native cases zero skips and inspected redacted artifact 12043906727. Complete affected local suites 88 passed; local full-gate environment limitation is explicit in archived verification. No deployment or target promotion claimed.
---

## Goal

Make REALITY target validation bounded standards-correct and truthful.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: A20; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
