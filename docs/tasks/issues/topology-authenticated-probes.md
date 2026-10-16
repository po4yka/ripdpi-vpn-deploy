---
id: MON-1791618056169855
title: Deliver topology-aware authenticated transport health and secure smoke probes
kind: feature
status: done
area: monitoring
priority: high
risk: high
owner: primary
parent: EPC-1791618453830051
blocked_by: [SCR-1791618039091425, ANS-1791618048083304, XRY-1791617955392712, SCT-1791617687019287]
spec_mode: required
openspec_change: topology-authenticated-probes
created: 2026-10-10
updated: 2026-10-17
related_tasks: [ANS-1791562764586678, SEC-1791471757439452, ANS-1791586652330612]
status_detail: Authenticated native topology, complete local and hosted source gates, closed AWG prerequisite, canonical arm64 acceptance and qualified federation passed.
closed_at: "2026-10-16T20:14:37Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Runtime df5c40554cb171f2b0acc6b275a65579a05d7806 passed full make check, all 89 CI jobs, eight authenticated topology cases and real hopping/warm adoption; AWG prerequisite committed done at 0e6bd844, two canonical arm64 matrices and consumer CI passed, clean federation validated 189 tasks.
---

## Goal

Deliver topology-aware authenticated transport health and secure smoke probes.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: A16, A17, A22; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
