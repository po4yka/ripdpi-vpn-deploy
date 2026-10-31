# CIC-1793457997498773: Merge every pull request by rebase and keep lifecycle commits in one pull request

## Objective

`main` accepts rebase merges only, CI validates every pull-request commit subject and trailer, `taskctl` no longer requires the review snapshot on a remote ref, and the lifecycle documentation says that review, terminal and purge commits may share one pull request as separate commits.

## Ownership

Primary: this repository. `.github/repository-policy.json`, `.github/workflows/ci.yml` (pr-title job), `scripts/check-pr-title.py`, `scripts/tasks/taskctl.py`, their tests, `docs/tasks/README.md`, `CONTRIBUTING.md`, `docs/how-to/branch-protection.md`, `docs/reference/testing.md`, the `openspec-archive-change` and `repo-task-board` skills and `tools/tasking/generated-assets.lock.json`. The `repository-rulesets` change artifacts are not edited; REQ-RPOL-MERGE is modified by delta. Single lane.

## Execution

- [ ] CIC-1793458205564841 Switch the repository policy to rebase-only merges, drop the squash settings, and validate every pull-request commit subject and trailer in the PR title job with tests #feature !high @item:CIC-1793457997498773
- [ ] CIC-1793458297726343 Remove the protected-ref gate and --protected-ref from taskctl close prepare and verify together with its tests, keeping the HEAD committed-review check #feature !high @item:CIC-1793457997498773
- [ ] CIC-1793458391172583 Document the rebase-only lifecycle in the task README, CONTRIBUTING, branch-protection and testing pages and the lifecycle skills, refresh the asset lock, and run focused pytest, docs-check, validate, make check and exact-head CI #chore !high @item:CIC-1793457997498773

## Verification

Local: `python3 -m pytest tests/unit/test_branch_protection_contract.py tests/unit/test_pr_title.py tests/unit/test_required_protective_workflows.py scripts/tests/test_taskctl.py tests/unit/test_task_contract_workflow.py tests/unit/test_agent_instructions.py`, `make docs-check`, `./taskctl validate`, `make check` once because the change spans CI, a shared script and skills. Remote CI: the pull request's full run at the exact head, including the `PR title` job on this pull request's own commits. Live: `make repository-policy-plan` and `make repository-policy-apply` are a separate authorized operator action and are recorded under `live` when run; until then `live` stays `required`. Dry-run, staging and client gates are not applicable. Artifact: the refreshed generated asset lock hash reviewed in the diff.
