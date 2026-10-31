---
name: openspec-archive-change
description: Archive a completed RIPDPI VPN deployment OpenSpec change through the fail-closed taskctl lifecycle. Use when implementation is complete, the task is in review, and the user asks to finalize or archive the change.
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

1. Resolve the active change with `./taskctl openspec cli list --json`. Find its linked portfolio task by filtering `./taskctl list --json` output for the task whose `openspec_change` field equals the change name — `./taskctl list --json` has no query flag for this.
2. Require portfolio status `review`, completed execution steps, final verification evidence, and a regenerated board; never treat an agent checkbox as acceptance.
3. Require the review-state issue, execution, verification, and board to be committed together before archival. If that committed review snapshot does not already exist, stop and ask for the review-state commit; resume this workflow only after it exists. Warning: `main` is squash-merge only, so the review snapshot, the terminal `done`/`dropped` commit, and the `close purge` deletion must each be merged as separate pull requests (separate first-parent commits); a single pull request holding review and done is squashed into one commit and makes the later purge unvalidatable.
4. Run `./taskctl verify <task-id> --archive-ready`. Stop on open mdtask steps, invalid OpenSpec artifacts, missing exact-SHA evidence, any `required`/`blocked` evidence category, or `review snapshot is not on origin/main`: that last refusal means the review pull request has not merged yet (or `origin` is stale); merge or fetch it, never bypass it with a throwaway `--protected-ref`.
5. Run `./taskctl openspec archive <change-name>`. Never call the upstream archive command directly, pass `--no-validate`, move a change directory manually, or proceed after a warning.
6. Run `./taskctl close prepare <task-id> --outcome done --evidence "<concise evidence summary>"`. It applies the same protected-ref check as step 4 and refuses without a reachable `origin/main`.
7. Stop and ask for the terminal-state commit. `close purge` is a later, separately committed step.

For a dropped task, prepare `dropped` with an explicit reason and commit it first. `./taskctl openspec archive <change-name>` then archives the change with `--skip-specs`, so incomplete behavior deltas never reach the main specs; commit the archive before `close purge`, which refuses an active or unarchived change. Do not delete the change directory instead.
