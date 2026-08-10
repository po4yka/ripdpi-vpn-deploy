---
id: SEC-1786336086885514
title: Resolve all open CodeQL code scanning alerts
kind: bug
status: review
area: security
priority: high
risk: high
owner: Code scanning remediation
parent: null
blocked_by: []
spec_mode: required
openspec_change: resolve-codeql-code-scanning-alerts
created: 2026-08-10
updated: 2026-08-10
related_tasks: []
status_detail: "Local gates and PR #70 required checks passed; current hosted CodeQL PR analysis reports zero Python results, with alerts 320-327 absent and replacement 328 fixed without dismissal."
---

## Goal

Eliminate all eight CodeQL alerts open on `main` at source SHA
`cfb52893594d4f7c9c9f423787f872f4935206ad` without dismissing findings,
weakening CodeQL queries, or breaking the local Xray metrics collector.

## Ownership

- Primary paths: the eight alerted Python files and focused tests under
  `tests/unit/`, `scripts/tests/`, and the monitoring role's Molecule scenario.
- Planning paths: this issue and
  `openspec/changes/resolve-codeql-code-scanning-alerts/`.
- The implementation stays isolated in the dedicated
  `codex/fix-current-code-scanning` worktree and preserves unrelated branches
  and worktrees.

## Acceptance criteria

- Alerts 320 through 327 are fixed in source; none is dismissed, suppressed,
  or hidden by weakening `.github/workflows/codeql.yml`.
- The Xray Prometheus textfile is not world-readable, remains readable by the
  node_exporter account through the shared textfile group, and continues to be
  produced atomically by the unprivileged Xray exporter.
- Expected bounded socket-readiness retries remain bounded and explicit, while
  exporter fallback-write failures emit a redacted diagnostic instead of being
  silently swallowed.
- Redundant imports and the overwritten taskctl execution-path assignment are
  removed without changing their surrounding behavior.
- Focused Python tests, monitoring Molecule coverage, task-contract validation,
  `make ci-fast`, and `make validate` pass locally, or an environment-only
  blocker is recorded with the exact failing command.
- The exact implementation SHA receives a successful hosted CodeQL Python run
  before the portfolio task can close; local validation alone is not treated as
  proof that GitHub has closed the alerts.
