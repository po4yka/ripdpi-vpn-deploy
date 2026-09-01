---
id: SEC-1788275314490012
title: Resolve current CodeQL and Scorecard code scanning alerts
kind: bug
status: review
area: security
priority: high
risk: high
owner: Code scanning remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: resolve-current-code-scanning-alerts
created: 2026-09-01
updated: 2026-09-01
related_tasks: []
status_detail: All eight alerts fixed without dismissal; exact main SHA 43aa5bf passed CodeQL, Scorecard, CI, image publication, and SARIF upload.
---

## Goal

Eliminate the eight open code-scanning alerts on `main` at
`bb889ed478d858e3606f60c8041e3c0d72bd8795`—Scorecard 341–344 and CodeQL
424, 511–513—at their causes without dismissal, scanner weakening, or behavior
regression.

## Ownership

- Python implementation and focused tests:
  `scripts/tailnet-network-promotion.py`,
  `scripts/vpn-protocol-liveness.py`,
  `tests/unit/test_tailnet_network_promotion.py`, and
  `tests/unit/test_protocol_liveness_sentinel.py`.
- Workflow implementation and contract test:
  `.github/workflows/publish-molecule-debian13.yml`,
  `.github/workflows/publish-molecule-ubuntu2404.yml`, and a focused file under
  `tests/unit/`.
- Planning and evidence:
  `openspec/changes/resolve-current-code-scanning-alerts/` and this issue.
- Dedicated branch/worktree: `codex/fix-code-scanning-20260901` at
  `/tmp/ripdpi-code-scanning-20260901`; the conflicted main checkout and all
  unrelated worktrees remain untouched.

## Acceptance criteria

- Alerts 341–344, 424, and 511–513 are fixed in source; none is dismissed,
  suppressed, or hidden by scanner configuration changes.
- Tailnet snapshot failures retain the canonical
  `terraform-snapshot-invalid` category when opening or closing a local
  descriptor fails, with no path, state, or raw exception disclosure.
- AWG configuration validation still runs before namespace mutation while the
  unused parse result is removed.
- Both Molecule image publication workflows are read-only at top level; only
  their publish job receives exact `contents: read`, `packages: write`, and
  `security-events: write` permissions.
- Focused tests, actionlint, repository-pinned zizmor, `make ci-fast`, and
  `make validate` pass locally, or exact environment-only blockers are recorded.
- The exact implementation SHA passes hosted CodeQL and Scorecard, GitHub marks
  all eight alerts `fixed`, and an authorized hosted run proves image publication
  plus SARIF upload before closure.
