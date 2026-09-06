---
id: CIC-1788630270264106
title: Restore vpnd release SBOM generation
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
created: 2026-09-05
updated: 2026-09-06
spec_reason: tooling-only
related_tasks: []
status_detail: Release SBOM generation delivered to protected main 9af5a963.
closed_at: "2026-09-06T04:58:37Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Protected main 9af5a963255614ff6851b79b4acd9aa9bc399886; GitHub checks 29 success, 1 neutral.
---

## Goal

Restore the release SBOM stage so vpnd publication receives a real Cargo
dependency inventory at its declared asset path. This tooling repair gates
the existing vpnd binary release; it changes no deployed runtime or secrets.

## Acceptance criteria

- Generate a CycloneDX SBOM from the real locked vpnd Cargo graph without
  production secrets, covering all Cargo targets and excluding dev dependencies.
- Stage the validated inventory at dist/sbom.json and reject missing output,
  generator errors, lockfile drift and unrelated product inventories.
- Exercise the same generator in required PR CI before the publishing boundary.
- Observe real generation and packaging-boundary regression tests, and deliver
  the fix to protected main after the required checks pass.
