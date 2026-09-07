---
name: openspec-archive-change
description: Archive a completed RIPDPI VPN deployment OpenSpec change through the fail-closed taskctl lifecycle.
allowed-tools: Bash(./taskctl:*)
license: MIT
compatibility: Requires the repository-pinned ./taskctl wrapper.
metadata:
  author: openspec
  version: "1.0-ripdpi"
  generatedBy: "1.8.0"
---

# Archive an OpenSpec change

Use this skill only when implementation is complete and the user asks to finalize a change.

1. Resolve the active change with `./taskctl openspec cli list --json` and its linked portfolio task with `./taskctl list --json`.
2. Require portfolio status `review`, completed execution steps, final verification evidence, and a regenerated board; never treat an agent checkbox as acceptance.
3. Require the review-state issue, execution, verification, and board to be committed together before archival. If that committed review snapshot does not already exist, stop and ask for the review-state commit; resume this workflow only after it exists.
4. Run `./taskctl verify <task-id> --archive-ready`. Stop on open mdtask steps, invalid OpenSpec artifacts, missing exact-SHA evidence, or any `required`/`blocked` evidence category.
5. Run `./taskctl openspec archive <change-name>`. Never call the upstream archive command directly, pass `--no-validate`, move a change directory manually, or proceed after a warning.
6. Run `./taskctl close prepare <task-id> --outcome done --evidence "<concise evidence summary>"`.
7. Stop and ask for the terminal-state commit. `close purge` is a later, separately committed step.

For a dropped task, do not archive incomplete behavior deltas as completed. Prepare `dropped` with an explicit reason and preserve the active change until the owner decides whether to revise or remove it.
