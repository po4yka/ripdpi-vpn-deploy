# CIC-1788741692326070: Require committed review before terminal close

## Objective

Reject done closure until the selected task has a committed `review` snapshot,
keep the canonical archive workflow executable, and make the guard read only
the selected historical record.

## Ownership

Primary owns `scripts/tasks/taskctl.py`, the existing taskctl regression suite,
the canonical OpenSpec archive skill and lock digest, and this task's portfolio
and OpenSpec records. Shared task files remain a serialized lane.

## Execution

- [x] CIC-1788741692344134 Add a failing command-level regression for an uncommitted review transition #bug !crit @item:CIC-1788741692326070
- [x] CIC-1788741818664643 Require the selected task HEAD snapshot to be committed in review before done closure #bug !crit @item:CIC-1788741692326070
- [x] CIC-1788741818900064 Run taskctl regressions and repository task validation #bug !crit @item:CIC-1788741692326070
- [x] CIC-1788747290039529 Route the closure contract through OpenSpec and commit the review-state workflow boundary #feature !crit @item:CIC-1788741692326070
- [x] CIC-1788747290653696 Read only the selected committed task record and prove bounded lookup #bug !crit @item:CIC-1788741692326070
- [x] CIC-1788747291263267 Run focused, full local, and protected pull-request validation #chore !crit @item:CIC-1788741692326070

## Verification

- Focused tests must prove refusal is no-write, committed review succeeds, and
  path or identity drift fails closed.
- A deterministic command-count regression must prove the guard performs one
  selected `git show` and no repository-wide issue-tree scan.
- The canonical skill and generated-asset lock must validate together.
- `./taskctl validate --base origin/main`, `make task-check`, `git diff --check`,
  the full local gate, and all protected PR checks must pass on the final SHA.
- Dry-run, staging, live, client, and artifact evidence are not applicable to
  repository-local task tooling and workflow documentation.
