---
id: XRY-1791617955392712
title: Align XHTTP endpoint paths forwarded attribution and served origins
kind: bug
status: review
area: xray-config
priority: high
risk: high
owner: primary
parent: EPC-1791618453830051
blocked_by: [SCT-1791617687019287]
spec_mode: required
openspec_change: xhttp-endpoint-contract
created: 2026-10-10
updated: 2026-10-14
related_tasks: [ANS-1791562764586678, ANS-1791586652330612]
status_detail: "Integrated main source 3010dfb517b84cd7fbe9c3512b30b87d63b64fe8 passed all 88 source/native CI jobs in 38792726270 and both CodeQL analyses; focused local evidence and the unsuccessful monolithic local attempt are recorded. No external rollout or real notification receipt claimed."
---

## Goal

Align XHTTP endpoint paths forwarded attribution and served origins.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: A11, A13, A15; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
