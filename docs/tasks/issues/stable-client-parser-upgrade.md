---
id: "TST-1791618376497512"
title: "Upgrade verified recipient parsers to the current stable client line"
kind: "feature"
status: "backlog"
area: "testing"
priority: "medium"
risk: "high"
owner: "primary"
parent: "EPC-1791618453830051"
blocked_by: ["TST-1791618356595983", "SCT-1791617687019287", "XRY-1791617955392712", "SCR-1791618039091425"]
spec_mode: "required"
openspec_change: "stable-client-parser-upgrade"
created: "2026-10-10"
updated: "2026-10-10"
related_tasks: []
---

## Goal

Upgrade verified recipient parsers to the current stable client line.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: upgrade / feature roadmap; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
