---
id: CIC-1793437852879654
title: Refuse done closure until the review snapshot is on the protected ref
kind: feature
status: backlog
area: ci
priority: high
risk: standard
owner: primary
parent: null
blocked_by: []
spec_mode: required
openspec_change: cic-1793437852879654-refuse-done-closure-until-the-review-snapshot-is-on-the-protected-ref
created: 2026-10-31
updated: 2026-10-31
related_tasks: []
---

## Goal

`./taskctl close prepare <id> --outcome done` and `./taskctl verify <id> --archive-ready` refuse while the committed `review` snapshot of the task is absent from the protected ref (default `origin/main`, override `--protected-ref`), so that under the squash-only merge policy the review snapshot, the terminal record and the purge always land as separate first-parent commits on `main` and the purge audit owned by `CIC-1788708456909496` stays satisfiable. The gate reports the task, the ref and the remedy; a missing ref fails closed without fetching.

## Acceptance criteria

- Done closure and archive-ready verification fail before writing any lifecycle artifact when the protected ref lacks the task record at its path, names another task ID, or holds it in a non-review state; the message names the task ID, the ref and the remedy.
- Both commands accept `--protected-ref`; an unresolvable ref fails closed naming the ref and the override; no fetch or ref mutation is attempted.
- Dropped closure, `close purge`, the purge audit and historical validation are unchanged, and the collapsed `doing -> done` transition is still rejected.
- `docs/tasks/README.md` and the archive and board skills name the gate; the generated asset lock is refreshed and `./taskctl validate` passes.
- Focused taskctl tests cover absent, stale, other-ID, present, missing-ref and override paths and pass locally and in CI at the exact head.
