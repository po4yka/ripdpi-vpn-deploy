---
id: "TST-1791618356595983"
title: "Deliver isolated native acceptance for every baseline transport"
kind: "feature"
status: "backlog"
area: "testing"
priority: "high"
risk: "high"
owner: "primary"
parent: "EPC-1791618453830051"
blocked_by: ["SEC-1791617841911853", "ANS-1791617913525586", "SCR-1791618039091425", "ANS-1791618048083304", "XRY-1791617955392712", "MON-1791618056169855", "SCT-1791617687019287", "SCR-1791617975137354"]
spec_mode: "required"
openspec_change: "native-four-protocol-acceptance"
created: "2026-10-10"
updated: "2026-10-10"
related_tasks: ["SEC-1791545689674403", "ANS-1791562764586678", "ANS-1791586652330612", "SEC-1791471757439452"]
---

## Goal

Deliver isolated native acceptance for every baseline transport.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: A03, A07, A08, A09, A12, A14, A22; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
