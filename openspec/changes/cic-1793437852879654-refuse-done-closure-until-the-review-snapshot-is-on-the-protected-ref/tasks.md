# CIC-1793437852879654: Refuse done closure until the review snapshot is on the protected ref

## Objective

`./taskctl close prepare <id> --outcome done` and `./taskctl verify <id> --archive-ready` refuse, with a message naming the task, the protected ref and the remedy, while the committed review snapshot is absent from the protected ref (default `origin/main`, override `--protected-ref`); a missing ref fails closed without fetching; dropped closure, purge and the purge audit are unchanged.

## Ownership

Primary: this repository. `scripts/tasks/taskctl.py` (`close prepare`, `verify`, parser), `scripts/tests/test_taskctl.py`, `tests/unit/test_task_contract_workflow.py`, `docs/tasks/README.md`, `.agents/skills/openspec-archive-change/SKILL.md`, `.agents/skills/repo-task-board/SKILL.md`, `tools/tasking/generated-assets.lock.json`. Single lane; no shared-file serialization with other active changes.

## Execution

- [x] CIC-1793437958813160 Refuse close prepare done and verify archive-ready while the review snapshot is absent from the protected ref, with --protected-ref override, fail-closed missing-ref handling and taskctl tests for absent, stale, other-ID, present and override paths #feature !high @item:CIC-1793437852879654
- [x] CIC-1793437959694888 Document the protected-ref prerequisite in the task README and the archive and board skills and refresh the generated asset lock hash #chore !high @item:CIC-1793437852879654
- [ ] CIC-1793437960612788 Run focused taskctl pytest, taskctl validate, task-check, docs-check and exact-head protected CI #chore !high @item:CIC-1793437852879654

## Verification

Local: `python3 -m pytest scripts/tests/test_taskctl.py tests/unit/test_task_contract_workflow.py tests/unit/test_agent_instructions.py`, `./taskctl validate`, `make task-check`, `make docs-check`; `make check` once because the change touches a shared script and skills. Remote CI: the pull request's full run at the exact head. Dry-run, staging, live and client gates are not applicable: no host, provider, client or deployment input changes. Artifact: the refreshed generated asset lock hash reviewed in the diff.
