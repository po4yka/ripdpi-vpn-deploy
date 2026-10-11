---
id: "ANS-1791618083683925"
title: "Deliver coordinated Hysteria ECH server and recipient profiles"
kind: "feature"
status: "backlog"
area: "ansible"
priority: "medium"
risk: "high"
owner: "primary"
parent: "EPC-1791618453830051"
blocked_by: ["SCR-1791618064422507", "TST-1791618376497512", "ANS-1791617913525586"]
spec_mode: "required"
openspec_change: "hysteria-ech-profiles"
created: "2026-10-10"
updated: "2026-10-10"
related_tasks: ["SEC-1791471757439452", "ANS-1791562764586678"]
---

## Goal

Deliver coordinated Hysteria ECH server and recipient profiles.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: A17, A22; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
