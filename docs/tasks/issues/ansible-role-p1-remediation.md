---
id: SEC-1791545689674403
title: Repair critical Ansible role audit security and availability paths
kind: bug
status: review
area: security
priority: critical
risk: high
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: ansible-role-p1-remediation
created: 2026-10-09
updated: 2026-10-09
related_tasks: []
status_detail: Source PR 282 prepared; exact source 2c3a311d passed all hosted workflows, local gates and independent review. Deployment acceptance remains outside this task.
---

## Goal

Repair the critical role authority and availability paths, preserve already
integrated resolver/collector fixes, and prepare a reviewed source PR.

## Acceptance criteria

- All eleven P1 audit paths are repaired or demonstrated already corrected on the selected source.
- Positive startup, backup, bounded notification and retained receiver behavior is exercised; refusal-only output does not satisfy capability acceptance.
- Role regressions, intended snapshots, required local gates and independent security review pass.
- Exact-source PR checks are recorded separately from deployment acceptance.
- Unrelated work and private inputs remain intact; no production or retired monitoring activation is performed.
