---
id: "XRY-1791617991738391"
title: "Deliver selectable alternate XHTTP endpoints and measured typed tuning"
kind: "feature"
status: "backlog"
area: "xray-config"
priority: "medium"
risk: "high"
owner: "primary"
parent: "EPC-1791618453830051"
blocked_by: ["XRY-1791617955392712", "ANS-1791617913525586", "SEC-1791617841911853", "TST-1791618356595983"]
spec_mode: "required"
openspec_change: "xhttp-alternate-and-tuning"
created: "2026-10-10"
updated: "2026-10-10"
related_tasks: ["ANS-1791562764586678", "ANS-1791586652330612"]
---

## Goal

Deliver selectable alternate XHTTP endpoints and measured typed tuning.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: upgrade / feature roadmap; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
