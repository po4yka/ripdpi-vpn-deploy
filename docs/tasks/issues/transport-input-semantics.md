---
id: "SCT-1791617687019287"
title: "Reject incoherent transport inputs before runtime mutation"
kind: "bug"
status: "backlog"
area: "secrets"
priority: "high"
risk: "high"
owner: "primary"
parent: "EPC-1791618453830051"
blocked_by: []
spec_mode: "required"
openspec_change: "transport-input-semantics"
created: "2026-10-10"
updated: "2026-10-10"
related_tasks: []
---

## Goal

Reject incoherent transport inputs before runtime mutation.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: A18; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
