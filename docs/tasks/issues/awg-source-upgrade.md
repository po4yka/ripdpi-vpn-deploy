---
id: "SCR-1791618073850409"
title: "Upgrade pinned AmneziaWG sources with unchanged reviewed wire settings"
kind: "feature"
status: "backlog"
area: "scripts"
priority: "medium"
risk: "high"
owner: "primary"
parent: "EPC-1791618453830051"
blocked_by: ["SCR-1791618039091425", "ANS-1791617913525586", "TST-1791618356595983"]
spec_mode: "required"
openspec_change: "awg-source-upgrade"
created: "2026-10-10"
updated: "2026-10-10"
related_tasks: ["ANS-1791562764586678", "SEC-1791471757439452"]
---

## Goal

Upgrade pinned AmneziaWG sources with unchanged reviewed wire settings.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: A07, A22; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
