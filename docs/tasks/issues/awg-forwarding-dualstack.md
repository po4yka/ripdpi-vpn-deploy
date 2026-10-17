---
id: ANS-1791618048083304
title: Deliver interface-correct dual-stack AmneziaWG forwarding and configurable MTU
kind: feature
status: done
area: ansible
priority: high
risk: high
owner: primary
parent: EPC-1791618453830051
blocked_by: [SCR-1791618039091425]
spec_mode: required
openspec_change: awg-forwarding-dualstack
created: 2026-10-10
updated: 2026-10-16
related_tasks: [ANS-1791562764586678, SEC-1791471757439452, "po4yka/RIPDPI#DAT-1792081130689287"]
status_detail: Exact-source Linux native and source gates, two canonical arm64 matrices, consumer CI and qualified federation passed.
closed_at: "2026-10-16T19:58:22Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Deployment df5c40554cb171f2b0acc6b275a65579a05d7806 passed full make check and all 89 CI jobs; six Linux native AWG cases and consumer 974cf06ab8d05e3b4275d0e98429a0d0de2bf598 passed two canonical arm64 matrices, hosted CI and 189-task federation.
---

## Goal

Deliver interface-correct dual-stack AmneziaWG forwarding and configurable MTU.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Android acceptance is arm64 emulator/native-core only at the owner's request; Linux native forwarding, revocation, no-leak and rollback gates remain required.
- Audit coverage: A10, A21; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
