---
id: VPD-1791615284178957
title: Replace vpnd with Python while preserving commands and security
kind: feature
status: review
area: vpnd
priority: high
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: replace-vpnd-with-python
created: 2026-10-10
updated: 2026-10-10
related_tasks: []
status_detail: PR 283 merged after all nine required checks passed; OpenSpec archived and specs synchronized. Terminal closure awaits the approved observability_agent historical-sample fixture remediation and green post-merge CI.
---

## Goal

Deliver a Python 3.12 `vpnd` with every existing command, flag, state format,
operator artifact and security guarantee preserved, then remove the authored
Rust implementation and its compiler-dependent development/release lanes.
Make remains the canonical operator surface. Implementation, PR merge and
OpenSpec archival are authorized; qrcode and tomli-w are approved. The bounded
observability_agent fixture remediation is also approved. Real fleet operations
remain outside this request.

## Acceptance criteria

1. All twelve top-level commands and nested host/fleet actions work through both
   the repository launcher and installed Python distribution; CLI parsing,
   defaults, environment overrides, exit status and structured output match the
   approved baseline contract.
2. Secret-file descriptor gates, redaction, private atomic outputs, validated
   Make assignments, exact inventory targeting and cleanup pass positive and
   adversarial regression tests. Explain mode performs no mutations or network
   operations, including local host registry changes.
3. Every existing Rust unit/integration/property/snapshot assertion and every
   Rust-dependent Python contract test maps to an executed Python equivalent.
   Compiler-specific checks are replaced by Python checks rather than reported
   as behavioral tests. No skipped cases or missing mappings count as parity.
4. Probe-matrix schema-3 reports, JSONL journals, timing, control/probe semantics,
   cancellation, process reaping and partial-result durability remain intact.
5. Linux/macOS on x86_64/arm64 pass installation and command/artifact tests using
   Python 3.12 without Cargo or rustc. New releases retain checksums, provenance,
   dependency SBOM, reproducibility verification and version consistency.
6. Active source, hooks, Make gates, CI/release workflows and dependency tooling
   no longer require Rust. Historical records remain intact; local operator
   configuration, secrets, state, caches and unrelated work remain untouched.
7. Full local gate, independent security review and terminal exact-SHA hosted
   checks pass before implementation closure. Planning validation alone does
   not satisfy any implementation acceptance criterion.
