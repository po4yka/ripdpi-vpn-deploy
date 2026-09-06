# CIC-1788708456909496

## Objective

Make local evidence-ownership links survive valid source-task purge while
invalid historical references and category substitutions fail closed.

## Ownership

Primary owns `scripts/tasks/taskctl.py`, existing task-contract tests,
`docs/tasks/README.md`, affected task ownership mappings, and this change.
Terraform, Ansible, secrets, providers, hosts, and clients are out of scope.

## Execution

- [x] CIC-1788708671401309 Add RED task-contract tests for valid and invalid historical related-task resolution, safe purge, graph projection, and client evidence policy #feature !high @item:CIC-1788708456909496
- [x] CIC-1788708671983805 Implement cached local terminal-history resolution and permit only safe incoming related-task edges across canonical done-task purge #feature !high @item:CIC-1788708456909496
- [x] CIC-1788708672560736 Update proportional evidence documentation and the structured ownership-mapping contract while preserving incomplete categories as required or blocked #feature !high @item:CIC-1788708456909496
- [x] CIC-1788708673268654 Verify dropped, malformed, invalid latest incarnation, parent, blocker, dirty-tree, and pre-commit purge failure paths remain fail-closed #bug !high @item:CIC-1788708456909496
- [ ] CIC-1788708673867480 Run focused pytest, taskctl validation, task-check, diff hygiene, clean-history review, and exact-head protected CI #chore !high @item:CIC-1788708456909496

## Verification

- Focused task-contract tests must demonstrate the new success path and every
  listed fail-closed boundary.
- `./taskctl validate --base origin/main`, `make task-check`, and
  `git diff --check` must pass locally.
- The final clean-history pull-request head must pass every protected required
  check. Dry-run, staging, live, client, and artifact execution are not
  applicable because this change modifies repository-local task tooling only.
