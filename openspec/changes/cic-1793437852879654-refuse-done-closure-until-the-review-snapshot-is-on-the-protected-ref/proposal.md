# Change: Refuse done closure until the review snapshot is on the protected ref

Task ID: `CIC-1793437852879654`

## Why

`main` accepts squash merges only and requires linear history, and the
committed-review purge audit validates the first-parent history of `main`.
`taskctl close prepare --outcome done` currently checks the review snapshot
only against `HEAD`, so a branch that commits the `review` snapshot and the
terminal `done` record in the same pull request passes every local gate and
is then squashed into one first-parent commit. `main` shows `doing` followed
directly by `done`, and the later `close purge` fails with
`invalid terminal transition doing -> done`; the terminal record cannot be
purged without an exception in the fail-closed audit. This happened for
`SEC-1793386547449444`. The README and lifecycle skills now state the
three-pull-request rule, but documentation is the only guard, and the error
surfaces only at purge time, when the history of `main` can no longer be
repaired. The committed-review policy and its purge audit are owned by
`CIC-1788708456909496`; this change extends that policy at the point where the
mistake is still cheap to correct.

## What Changes

- `./taskctl close prepare <id> --outcome done` refuses, before any lifecycle artifact is written, when the selected task record on the protected ref (default `origin/main`) is absent, names another task ID, or is not in `status: review`. The message names the task, the protected ref, and the required action: merge the review snapshot as its own pull request, or fetch the remote, before preparing done closure.
- `./taskctl verify <id> --archive-ready` reports the same refusal, so the archive workflow stops before `openspec archive` instead of at `close prepare`.
- Both commands accept `--protected-ref <ref>` to name another protected ref; a missing or unreadable ref fails closed with a message that names the ref. `taskctl` never fetches.
- `dropped` closure, `close purge`, the purge audit and historical validation are unchanged.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `ci/task-contract-validation`: done closure and archive-ready verification require the committed review snapshot to be present on the protected ref, not only in `HEAD`.

## Impact

- `scripts/tasks/taskctl.py` (`close prepare`, `verify`, argument parsing), `scripts/tests/test_taskctl.py` and `tests/unit/test_task_contract_workflow.py` (fixture gains a protected ref), `docs/tasks/README.md`, the `openspec-archive-change` and `repo-task-board` skills and `tools/tasking/generated-assets.lock.json`.
- Operator-visible CLI behaviour: an archive or done closure prepared in a checkout whose `origin/main` is stale or lacks the review snapshot now stops with an explicit message. No Terraform, Ansible, secrets, schema, provider, host or client contract changes.
