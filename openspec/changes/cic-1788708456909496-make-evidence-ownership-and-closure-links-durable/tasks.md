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
- [x] CIC-1788708673867480 Run focused pytest, taskctl validation, task-check, diff hygiene, clean-history review, and exact-head protected CI #chore !high @item:CIC-1788708456909496

## Verification

- Focused task-contract tests must demonstrate the new success path and every
  listed fail-closed boundary.
- `./taskctl validate --base origin/main`, `make task-check`, and
  `git diff --check` must pass locally.
- The final clean-history pull-request head must pass every protected required
  check. Dry-run, staging, live, client, and artifact execution are not
  applicable because this change modifies repository-local task tooling only.
- [x] CIC-1788729192473052 Add RED regressions for unmapped evidence transfers in merged lanes and purged historical related targets #bug !high @item:CIC-1788708456909496
- [x] CIC-1788729193073535 Validate evidence-transfer history consistently across active merged lanes and terminal related-task resolution #bug !high @item:CIC-1788708456909496
- [x] CIC-1788731559342267 Reject repaired malformed intermediate snapshots in historical resolution and deletion validation #bug !high @item:CIC-1788708456909496
- [x] CIC-1788733500688116 Reject later malformed merged reincarnations after a valid first-parent purge #bug !high @item:CIC-1788708456909496
- [x] CIC-1788733501332318 Validate archived OpenSpec requirement evidence before resolving historical links #bug !high @item:CIC-1788708456909496
- [x] CIC-1788733501927997 Parse escaped Markdown delimiters in shared evidence acceptance commands #bug !high @item:CIC-1788708456909496
- [x] CIC-1788737705846578 Validate multiple purged task IDs without corrupting the shared terminal-history index #bug !high @item:CIC-1788708456909496
