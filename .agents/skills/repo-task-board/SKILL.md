---
name: repo-task-board
description: Contract for RIPDPI VPN deployment tracked work (portfolio tasks, bugs, epics, OpenSpec-backed changes) covering file locations, taskctl-only lifecycle, stable IDs, and prohibitions. Use for triage, review, or closing work, or whenever the rules themselves matter; narrower skills own creating, starting, implementing, and archiving.
---

# Repository task board

`docs/tasks/issues/*.md` is the portfolio source of truth. `docs/tasks/board.md` is generated. Execution lives in exactly one of:

- simple work: `docs/tasks/work/<TASK-ID>.md`;
- specification-driven work: `openspec/changes/<change>/tasks.md`.

Narrower skills own the individual steps: `mdtask-create` (new work), `mdtask-next` (pick and start), `sdd` (whether OpenSpec is required), `openspec-propose` / `openspec-apply-change` (plan and implement a change), `openspec-archive-change` (finalize), `mdtask` (execution checkboxes).

Use only `./taskctl` for lifecycle operations:

- inspect: `list`, `show`, `ready`, `graph`;
- create/start/update: `new`, `start`, `transition`, `steps`;
- validate: `verify`, `validate`, `generate-board`;
- complete: commit the task, execution, verification, and regenerated board in `review`; then `verify <task-id> --archive-ready`, `openspec archive <change>`, `close prepare <task-id> --outcome done --evidence "<summary>"`, commit, and later `close purge` in a separate commit;
- drop: `close prepare <task-id> --outcome dropped --evidence "<summary>" --reason "<why>"` and commit its receipts. Archive or remove a linked OpenSpec change only when its owner decides to (never archive incomplete deltas as completed), then `close purge` before the deletion commit.

Stable IDs are area-prefixed with globally unique 16-digit numeric suffixes. Worktrees share a locked allocator reservation through the Git common directory; committed validation catches cross-clone collisions. Local references use stable IDs; cross-repository references use qualified IDs such as `po4yka/RIPDPI#TRN-...`. `blocked_by` is canonical; reverse `blocks` is derived locally or through `./taskctl federation`. OpenSpec-mandatory categories are listed in the `sdd` skill; high-risk work can never waive it. Never hand-edit the generated board, use direct upstream archive, pass `--no-validate`, close work without evidence, or delete a record before its terminal-state commit exists.

Before parallel agents write, record owned paths and serialized shared-file lanes in the execution file's `## Ownership` section. Implementation work uses a dedicated worktree.
