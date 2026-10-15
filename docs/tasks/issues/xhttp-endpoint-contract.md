---
id: XRY-1791617955392712
title: Align XHTTP endpoint paths forwarded attribution and served origins
kind: bug
status: done
area: xray-config
priority: high
risk: high
owner: primary
parent: EPC-1791618453830051
blocked_by: [SCT-1791617687019287]
spec_mode: required
openspec_change: xhttp-endpoint-contract
created: 2026-10-10
updated: 2026-10-15
related_tasks: [ANS-1791562764586678, ANS-1791586652330612]
status_detail: "Implementation, independent review and exact-source checks passed; PR #297 prepared for owner review."
closed_at: "2026-10-15T16:37:25Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Source 7a08fcd7052351ef968988c2b79a0c57a33060aa passed complete local gates and exact-source hosted native/client acceptance recorded in verification. Integrated main 923304729f6bdd32edce6a9b6ceada1d51c7d011 revalidated both actual native endpoint cases plus all 138 baseline and four runtime acceptance cases in CI 38759230876. No external rollout or private-input migration claimed.
---

## Goal

Align XHTTP endpoint paths forwarded attribution and served origins.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: A11, A13, A15; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
