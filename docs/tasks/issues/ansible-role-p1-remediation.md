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
updated: 2026-10-12
related_tasks: []
status_detail: "Accepted integrated runtime source cf01f94a640913412f3316b5cb288881639712ce passed all 86 protected-main jobs in run 38134843683. Recorded verification results and external scope qualifications are preserved."
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
