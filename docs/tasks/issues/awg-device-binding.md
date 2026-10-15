---
id: SCR-1791618039091425
title: Deliver authoritative AmneziaWG device enrollment and client bindings
kind: feature
status: review
area: scripts
priority: high
risk: high
owner: primary
parent: EPC-1791618453830051
blocked_by: [SCT-1791617687019287]
spec_mode: required
openspec_change: awg-device-binding
created: 2026-10-10
updated: 2026-10-15
related_tasks: [ANS-1791562764586678, SEC-1791471757439452]
status_detail: "Integrated main source 3010dfb517b84cd7fbe9c3512b30b87d63b64fe8 passed all 88 source/native CI jobs in 38792726270 and both CodeQL analyses; focused local evidence and the unsuccessful monolithic local attempt are recorded. No external rollout or real notification receipt claimed."
---

## Goal

Deliver authoritative AmneziaWG device enrollment and client bindings.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete all named accepted/failure/security/rollback/privacy tests and exact-SHA source/CI evidence without weakening a gate.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: A05, A06; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.

## Source acceptance scope (2026-10-15)

Per the owner-approved criteria revision, source acceptance requires focused Mac
regressions, snapshots, full-history/staged gitleaks and complete unchanged
exact-SHA hosted source/native checks. The local monolithic attempt failed on a
registry timeout; its retry was cancelled after 32 minutes still queued. No full
local success is claimed; global and deployment gates remain unchanged.
