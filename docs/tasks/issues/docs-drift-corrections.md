---
id: DOC-1787497353178231
title: Correct documented-but-absent controls and stale docs
kind: bug
status: backlog
area: docs
priority: medium
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-08-23
spec_reason: docs-only
related_tasks: []
---

## Goal

Documentation no longer claims controls that do not exist and records hazards deferred to sibling changes: geo-block claim corrected, naive credential-delivery pitfall matches reality, cascade scaffold routing hazard documented, canonical decoy-site tree recorded, mirror snapshot-path contract pinned in prose.

## Acceptance criteria

- All six execution checkboxes in docs/tasks/work/DOC-1787497353178231.md are checked.
- grep over role docs finds no remaining documented-but-absent control names from the audit list.
- Documentation-only diff: no code, template, or default changes.
