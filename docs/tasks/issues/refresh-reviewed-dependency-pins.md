---
id: CIC-1792759317705110
title: Refresh reviewed dependency pins and integrate pending updates
kind: chore
status: done
area: ci
priority: high
risk: standard
owner: dependency-maintainer
parent: null
blocked_by: [ANS-1792773060904443]
spec_mode: not-required
openspec_change: null
created: 2026-10-23
updated: 2026-10-24
spec_reason: dependency-only
related_tasks: [ANS-1792773060904443]
status_detail: Dependency integration and complete source validation passed; ready for closure.
closed_at: "2026-10-24T09:06:57Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: Reviewed dependency updates are integrated in main. PR 380 fixes the local source cleanup failures; full make check passed at dd9fef311cde792af2a2d94ff0ee5c7f7427e6e9, with an identical tree at integrated ec655f037b5a1b7a26d8ddf4c673ef4e55791701. Hosted run 40069354263 passed all required checks. The linked ANS task is complete.
---

## Goal

Integrate the five pending dependency PRs and apply reviewed stable dependency fixes with complete local and hosted source validation.

## Acceptance criteria

- Preserve all five original dependency PR heads in the integrated history.
- Synchronize reviewed stable pins and generated hashes across consumers.
- Pass the complete local gate and protected PR checks before merging to main.
- Preserve unrelated work and require no fleet, credential, or operator-state mutation.
