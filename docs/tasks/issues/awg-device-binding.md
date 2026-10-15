---
id: SCR-1791618039091425
title: Deliver authoritative AmneziaWG device enrollment and client bindings
kind: feature
status: done
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
status_detail: "Address five additional PR #298 review findings in binding authority, interface names, duplicate devices, Make defaults and AWG reissuance."
closed_at: "2026-10-15T17:20:19Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Exact source f6ad803e97237d8d8ec3839284d84db974ea986c passed CI 38768887914: 88 successful jobs and 93 successful checks. Actual two-instance AWG traffic export rejection and revocation plus 61 encrypted Mac regressions passed. Approved source gate and honest failed local monolithic outcome are recorded; no deployment or private-input migration."
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
