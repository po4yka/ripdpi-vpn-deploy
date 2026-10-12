---
id: SCT-1791617687019287
title: Reject incoherent transport inputs before runtime mutation
kind: bug
status: done
area: secrets
priority: high
risk: high
owner: primary
parent: EPC-1791618453830051
blocked_by: []
spec_mode: required
openspec_change: transport-input-semantics
created: 2026-10-10
updated: 2026-10-12
related_tasks: []
status_detail: Accepted integrated runtime source cf01f94a640913412f3316b5cb288881639712ce passed all 86 protected-main jobs in run 38134843683. Recorded verification results and external scope qualifications are preserved.
closed_at: "2026-10-11T22:21:55Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Integrated runtime source cf01f94a640913412f3316b5cb288881639712ce passed all 86 protected-main jobs in run 38134843683. Recorded requirement-specific verification and external qualifications are preserved. Complete local gate components passed: 6,340 portable tests, 22 subtests, 297 CLI tests, 206 baseline transfers and 57 shell tests. Every assertion and deadline is retained; production code is unchanged."
---

## Goal

Reject incoherent transport inputs before runtime mutation.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: A18; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
