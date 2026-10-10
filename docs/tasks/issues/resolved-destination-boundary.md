---
id: "SEC-1791617841911853"
title: "Enforce resolved destination isolation for P0 P1 and Hysteria2"
kind: "bug"
status: "backlog"
area: "security"
priority: "critical"
risk: "high"
owner: "primary"
parent: "EPC-1791618453830051"
blocked_by: ["SCT-1791617687019287"]
spec_mode: "required"
openspec_change: "resolved-destination-boundary"
created: "2026-10-10"
updated: "2026-10-10"
related_tasks: ["SEC-1791471757439452", "SEC-1791545689674403", "ANS-1791562764586678"]
---

## Goal

Enforce resolved destination isolation for P0 P1 and Hysteria2.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: A01, A02; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
