---
name: mdtask-next
description: Select and start the next unblocked RIPDPI VPN deployment portfolio task. Use when the user asks what to work on next or to start the next task.
---

# Select the next task

1. Run `./taskctl ready --json` and rank by critical, high, medium, then low priority.
2. Confirm the task has no unresolved portfolio blockers. `./taskctl show <task-id>` prints the portfolio record and only the path of its execution file, so open that file and read its Objective, Ownership, and Execution steps before starting. A task missing from `ready` only because of a qualified cross-repository blocker (`owner/repo#ID`) may still be startable: check `./taskctl federation ready --peer-root <RIPDPI checkout>` to see whether the peer resolves it.
3. Declare file/module ownership and serialized shared-file lanes before parallel work begins.
4. Run `./taskctl start <task-id> --owner <role>` and `./taskctl generate-board`.
5. Execute through the relevant mdtask or OpenSpec skill in a dedicated worktree.

Do not auto-select blocked work or infer that a parent epic blocks its child.
