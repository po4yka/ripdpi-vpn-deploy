## Context

`require_committed_review` in `scripts/tasks/taskctl.py` reads the selected
task record from `HEAD` and requires `status: review` with the same task ID.
`command_close_prepare` calls it for `--outcome done`; `command_verify` with
`--archive-ready` runs `verify_task(archive_ready=True)` and performs no
committed-review check. Purge validation (`resolve_terminal_task`,
`validate_deleted_history`) walks the first-parent history of the trusted base
and rejects `doing -> done`, which is exactly what a squash merge of a
review-plus-done pull request produces. The repository policy allows squash
merges only, so the review snapshot must be a separate first-parent commit on
`main` before the terminal commit lands. `close purge` already takes
`--trusted-base`; no protected ref is configured in `tools/tasking/project.json`.
The policy owner `CIC-1788708456909496` is referenced in text only: its own
terminal history is a pre-activation `doing -> done` transition that the
historical resolver accepts only with a trusted base, so a `related_tasks`
edge to it cannot pass plain `./taskctl validate`.

## Goals / Non-Goals

- Goal: make the three-pull-request ordering a hard, early gate: a done closure (and archive-ready verification) refuses while the review snapshot is only in local branch history.
- Goal: a precise, actionable message naming the task, the protected ref and the remedy.
- Non-goal: changing the purge audit, `close purge`, historical validation or accepting a collapsed `doing -> done` transition.
- Non-goal: fetching or otherwise touching remote state from `taskctl`.
- Non-goal: a repository-config knob for the protected ref; `--protected-ref` on the two commands mirrors `close purge --trusted-base`.

## Decisions

- Check content at the protected ref, not commit ancestry: `git show <protected-ref>:<task path>` is parsed with `read_document` and must yield the same task ID with `status: review`. This answers the actual question (is the review snapshot on `main`?) with no first-parent archaeology, and it also holds when the record on `main` is a later review-state edit. Rejected: locating the first review commit in `HEAD`'s history and testing `merge-base --is-ancestor` against the ref, which is more code and fails on amended review commits that are already merged.
- One helper, `require_review_on_protected_ref(root, document, ref)`, called from `command_close_prepare` (done branch, after `require_committed_review`) and from `command_verify` when `--archive-ready` is set. `verify_task` is left alone so `openspec archive`'s internal archive-readiness check for dropped tasks keeps its scope. Rejected: extending `require_committed_review` itself, which `openspec archive` does not call and which would widen the dropped path.
- Default ref `origin/main`; `--protected-ref` on `close prepare` and `verify`. A ref that `git rev-parse --verify` cannot resolve fails closed with the ref and the override named. No implicit fallback to local `main`: a local `main` can be behind or ahead of the protected branch.
- Staleness is the operator's responsibility: the check reads the local remote-tracking ref and the message tells the operator to fetch. A stale ref that already shows `review` is still correct, because the review commit is then on `main` ahead of any terminal commit.
- Message text: `<id>: review snapshot is not on <ref>; merge the review commit as its own pull request (or fetch origin) before preparing done closure` and `<id>: protected ref <ref> is not available; fetch it or pass --protected-ref`.

## Contracts and ownership

- Scripts: `scripts/tasks/taskctl.py` (`require_review_on_protected_ref`, `command_close_prepare`, `command_verify`, parser arguments for `close prepare` and `verify`).
- Tests: `scripts/tests/test_taskctl.py` next to `test_done_close_requires_committed_review_snapshot` and `test_done_close_accepts_committed_review_snapshot`; the `TaskctlFixture` repository gains a `refs/remotes/origin/main` ref so existing done-closure tests keep passing, with cases for absent, stale (`doing`), other-ID, present, missing-ref and `--protected-ref` paths. `tests/unit/test_task_contract_workflow.py` keeps its skill-ordering test; the workflow docs test is extended for the new prerequisite sentence.
- Documentation: `docs/tasks/README.md` lifecycle paragraph, `.agents/skills/openspec-archive-change/SKILL.md` steps 3 to 6 and `.agents/skills/repo-task-board/SKILL.md` complete bullet name the protected-ref gate; the generated asset lock hash for the archive skill is refreshed; `docs/reference/make-targets.md` and `vpnd` references are untouched.
- No Terraform, Ansible, secrets, schema, vpnd or client contract is affected.

## Risks / Trade-offs

- Existing local workflows that archive and close in one branch right after committing review now stop at `verify --archive-ready` → the message names the remedy; the README already requires the separate review pull request.
- Fresh clones, worktrees without a remote, and CI checkouts lack `origin/main` → fail closed with the override named; CI never runs `close prepare` or `verify --archive-ready`, and validation (`./taskctl validate`) is untouched.
- A reviewer could pass a throwaway `--protected-ref` to bypass the gate → the override is explicit, visible in the command, and the purge audit on `main` remains fail-closed as the final check.

## Migration Plan

Forward: land the guard and its documentation in one pull request; tasks already in `review` on `main` are unaffected, tasks whose review snapshot is only on a branch must merge it first. Rollback: revert the commit; no data, receipt or history format changes. No provider, schema or runtime rollout gates apply.
