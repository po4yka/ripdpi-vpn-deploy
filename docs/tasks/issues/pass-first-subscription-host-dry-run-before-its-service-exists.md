---
id: ANS-1791461761742804
title: Pass first subscription host dry-run before its service exists
kind: bug
status: dropped
area: ansible
priority: high
risk: standard
owner: operator
parent: null
blocked_by: []
spec_mode: required
openspec_change: ans-1791461761742804-pass-first-subscription-host-dry-run-before-its-service-exists
created: 2026-10-08
updated: 2026-10-08
related_tasks: []
closed_at: "2026-10-08T15:25:23Z"
closed_reason: Owner cancelled acceptance and requested removal of all acceptance resources
evidence_summary: Live acceptance is cancelled, not completed. Already merged implementation is preserved; temporary provider and local acceptance resources are being retired.
---

## Goal

Pass the required first subscription-host dry-run before its systemd unit exists, while preserving loaded-unit checks and normal deployment activation.

## Acceptance criteria

- Fresh check mode defers activation and restart only after the exact unit template plans installation.
- Unknown discovery and unplanned absence refuse; loaded units retain systemd validation.
- Real role convergence and exact-source CI pass.
- The actual first P1 dry-run, deploy, verify/security and authenticated XHTTP pass before closing the task.
