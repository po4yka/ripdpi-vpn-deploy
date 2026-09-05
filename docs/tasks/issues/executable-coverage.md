---
id: CIC-1788643607572240
title: Execute native runtime and Go coverage in required CI
kind: bug
status: done
area: ci
priority: high
risk: standard
owner: Codex
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-09-06
updated: 2026-09-06
spec_reason: tooling-only
related_tasks: []
status_detail: Native and Go required coverage delivered to protected main e59cf6d5 with exact-main CI 33998219035.
closed_at: "2026-09-05T23:43:59Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Protected main e59cf6d529d4e9ea141e9de80512079d6262ee26; exact-main CI 33998219035, CodeQL 33998218924 and Scorecard 33998218864 succeeded.
---

## Goal

Execute the existing Terraform, native Alertmanager, metrics-permissions and
Go helper tests in required CI, with explicit portable/native test selection.

## Acceptance criteria

- Four native tests execute with pinned tools and actual UID/GID capabilities;
  missing dependencies and skipped selected tests fail the required lane.
- All 53 taskctl tests in `scripts/tests/` join the mandatory portable pytest gate.
- Six Go helper tests run locally through Make and in required CI without network
  probes, dependency lockfile mutation or cached test results.
- Scanner post-processing has executable offline regressions; public TLS scanning
  is documented as an operator integration rather than counted placeholder coverage.
- Observe hosted CI and deliver through protected main, preserving the original
  dirty checkout and serializing integration after PR159 releases main.
