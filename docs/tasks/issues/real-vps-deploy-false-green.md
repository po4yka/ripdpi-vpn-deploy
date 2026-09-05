---
id: CIC-1788632749680598
title: Fail real-VPS deploy when selected templates are missing
kind: bug
status: review
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
status_detail: Implementation and required hosted CI delivered to protected main 49f83c9b.
---

## Goal

Repair the real-VPS CI status boundary: selected deployments with missing
configuration must fail before provisioning, never report successful no-ops.
This narrow workflow regression fix changes no provisioning or runtime code.

## Acceptance criteria

- Keep Debian mandatory and select optional Ubuntu explicitly before job creation.
- Fail selected entries with actionable secret names when their template is absent.
- Remove the skip-output path around deploy and retain failure-propagating cleanup.
- Exercise the actual preflight shell on missing and present templates, validate
  workflow/security contracts and deliver through required CI to protected main.
- Preserve environment approval and avoid provisioning resources for this repair.
