---
id: CIC-1787209937108078
title: Restore dependency PR CI compatibility gates
kind: bug
status: done
area: ci
priority: high
risk: high
owner: codex
parent: null
blocked_by: []
spec_mode: required
openspec_change: cic-1787209937108078-restore-dependency-pr-ci-compatibility
created: 2026-08-20
updated: 2026-08-20
related_tasks: []
status_detail: "Hosted CI passed on main after merging dependency PRs #75 and #79."
closed_at: "2026-08-20T09:58:47Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "https://github.com/po4yka/ripdpi-vpn-deploy/actions/runs/32356133238"
---

## Goal

Restore green required CI checks for compatible dependency pull requests
without bypassing task-contract or image-security controls.

## Acceptance criteria

- Local task-contract history validation succeeds without the retired peer.
- The Debian 13 Molecule image is immutable, scan-clean for fixed HIGH and
  CRITICAL findings, and used by every Debian 13 scenario.
- Hosted CI is green on the repair, Dependabot PR #75, and PR #79, which
  superseded Dependabot PR #76 after it was closed as stale, before merge.
