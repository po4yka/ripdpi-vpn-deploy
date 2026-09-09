---
id: DOC-1787497353178231
title: Correct documented-but-absent controls and stale docs
kind: bug
status: done
area: docs
priority: medium
risk: standard
owner: po4yka
parent: null
blocked_by: []
spec_mode: not-required
openspec_change: null
created: 2026-08-23
updated: 2026-09-09
spec_reason: docs-only
related_tasks: []
closed_at: "2026-09-09T02:26:56Z"
closed_reason: All acceptance criteria and required evidence passed.
evidence_summary: "Local gates: make ci-fast targets green in the worktree (actionlint, zizmor, cloud-init schema, tf-test, tf-policy, yamllint, shellcheck, vpnd-deny, MSRV, 139 golden snapshots, secrets schema, bundle contract, full bats suite, vpnd clippy -D warnings and debug/release tests); make validate green; taskctl validate + make task-check green (9 tasks). Remote CI: exact-main ci.yml run on 2c5544fe20471bc43c649aef2278e3efe34503b6 merged via PR #211 with all pytest groups, codeql and required checks green."
---

## Goal

Documentation no longer claims controls that do not exist and records hazards deferred to sibling changes: geo-block claim corrected, naive credential-delivery pitfall matches reality, cascade scaffold routing hazard documented, canonical decoy-site tree recorded, mirror snapshot-path contract pinned in prose.

## Acceptance criteria

- All six execution checkboxes in docs/tasks/work/DOC-1787497353178231.md are checked.
- grep over role docs finds no remaining documented-but-absent control names from the audit list.
- Documentation-only diff: no code, template, or default changes.
