---
id: SCR-1791618188806822
title: Detect client payload drift from every consumed private input
kind: bug
status: doing
area: scripts
priority: high
risk: high
owner: primary
parent: EPC-1791618453830051
blocked_by: [SCR-1791618039091425, XRY-1791617955392712]
spec_mode: required
openspec_change: client-consumed-payload-identity
created: 2026-10-10
updated: 2026-10-16
related_tasks: []
status_detail: "Integrate the already coordinated AWG dual-stack producer from PR #304 to clear downstream contract drift; prove consumed IPv4/IPv6 and MTU changes, retain partial-publication safety, and rerun complete source gates for PR #302."
---

## Goal

Detect client payload drift from every consumed private input.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: A19; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
