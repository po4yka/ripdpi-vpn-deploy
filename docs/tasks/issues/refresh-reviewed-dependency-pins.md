---
id: CIC-1792759317705110
title: Refresh reviewed dependency pins and integrate pending updates
kind: chore
status: review
area: ci
priority: high
risk: standard
owner: dependency-maintainer
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-10-23
updated: 2026-10-23
spec_reason: dependency-only
related_tasks: []
---

## Goal

Integrate the five pending dependency PRs and apply reviewed stable dependency fixes with complete local and hosted source validation.

## Acceptance criteria

- Preserve all five original dependency PR heads in the integrated history.
- Synchronize reviewed stable pins and generated hashes across consumers.
- Pass the complete local gate and protected PR checks before merging to main.
- Preserve unrelated work and require no fleet, credential, or operator-state mutation.
