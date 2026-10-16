---
id: SCR-1791618073850409
title: Build and validate upgraded AmneziaWG sources locally
kind: feature
status: dropped
area: scripts
priority: medium
risk: high
owner: primary
parent: EPC-1791618453830051
blocked_by: [ANS-1791617913525586]
spec_mode: required
openspec_change: awg-source-upgrade
created: 2026-10-10
updated: 2026-10-16
related_tasks: [ANS-1791562764586678, SEC-1791471757439452, SCR-1791618039091425, TST-1791618356595983]
status_detail: All three PR review fixes and local lab manifest placement validated; updated ARM64 lab and complete make check passed.
closed_at: "2026-10-16T13:18:31Z"
closed_reason: Superseded by EPC-1792155716043904 after the owner selected integrated local completion without external soak or recipient-device acceptance.
evidence_summary: Positive implementation and genuine source/runtime observations are retained. The local successor owns all 45 positive requirements and remains open until its complete native and source gates pass; no missing external observation is relabelled as passed.
---

## Goal

Build and exercise the exact upgraded and retained source pairs in a disconnected local Linux lab; production defaults remain unchanged.

## Acceptance criteria

- Deliver the positive runnable behavior and every requirement in the linked OpenSpec delta; refusal-only or fixture-only output is insufficient.
- Complete real local builds, mixed-version authenticated traffic/captures, reconnects, warm pair/unit adoption, failure compensation, unchanged repeat and unrelated-tunnel preservation.
- Run local source gates; physical Android, fleet/staging and hosted runtime infrastructure are excluded from the revised local scope authorized on 2026-10-15, not represented as passing local evidence.
- Preserve inherited source fixes and all unrelated work; implementation and external execution need separate authorization.
- Audit coverage: A07, A22; baseline `605ae0be18dcbe1c55e3e7d8658131b2e0c201d3`.
- Dependency and acceptance details: linked design.md and verification.md.
