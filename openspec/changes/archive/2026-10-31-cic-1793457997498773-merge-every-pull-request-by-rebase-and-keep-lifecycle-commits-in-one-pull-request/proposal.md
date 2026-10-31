# Change: Merge every pull request by rebase and keep lifecycle commits in one pull request

Task ID: `CIC-1793457997498773`

## Why

`main` currently allows squash merges only. A squash collapses a pull request
into one first-parent commit, while the task-contract audit proves a task's
lifecycle from the first-parent history of `main`: a committed `review`
snapshot must precede the terminal `done` commit, and the `done` commit must
precede its purge. The two rules together force three pull requests per task
(review, terminal record, purge), guarded since `CIC-1793437852879654` by a
protected-ref check in `close prepare`. CONTRIBUTING already promises that
lifecycle pull requests "keep their separate commits through the allowed linear
rebase merge", which the ruleset does not allow. The owner has decided to make
rebase the only merge method: every pull-request commit then lands on `main`
unchanged as its own first-parent commit, linear history is preserved, the
audit keeps its proof, and one pull request can carry the whole lifecycle.

## What Changes

- BREAKING: `main` accepts rebase merges only (`allow_rebase_merge: true`, squash and merge commits disabled, `allowed_merge_methods: ["rebase"]`); linear history, resolved conversations, auto-merge and merged-branch deletion stay.
- BREAKING: every commit in a pull request becomes a release-please input, so CI validates each commit subject in the pull request (Conventional Commit form, no trailing period, no `Co-authored-by` trailer, no Codex metadata) in addition to the PR title. The PR title no longer becomes a commit subject.
- The review snapshot, terminal `done`/`dropped` record and `close purge` deletion may travel in one pull request as separate commits; they must never be squashed locally. The protected-ref gate (`--protected-ref`, the `origin/main` check in `close prepare --outcome done` and `verify --archive-ready`) is removed; `close prepare` keeps requiring the review snapshot committed in `HEAD`.
- Documentation (task README, CONTRIBUTING, branch-protection how-to, testing reference, `openspec-archive-change` and `repo-task-board` skills) describes the rebase-only lifecycle.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `repository-policy`: REQ-RPOL-MERGE changes from squash-only merging with PR-title subjects to rebase-only merging with per-commit subject validation. The requirement lives in the active `repository-rulesets` change (`CIC-1792911952227614`, in review); this change's delta modifies it and must archive after that change.
- `ci/task-contract-validation`: the three protected-ref requirements (REQ-CIC-1793437852879654-001..003) are removed; one requirement states that lifecycle transitions stay separate commits and may share a pull request.

## Impact

- `.github/repository-policy.json`, `tests/unit/test_branch_protection_contract.py` (the configuration command itself is unchanged; applying the policy is a separate authorized `make repository-policy-apply`).
- `scripts/check-pr-title.py`, `tests/unit/test_pr_title.py`, the `PR title` job in `.github/workflows/ci.yml` (full-history checkout for the commit range).
- `scripts/tasks/taskctl.py`, `scripts/tests/test_taskctl.py`.
- `docs/tasks/README.md`, `CONTRIBUTING.md`, `docs/how-to/branch-protection.md`, `docs/reference/testing.md`, the two lifecycle skills and `tools/tasking/generated-assets.lock.json`.
- Operator-visible: merges use the "Rebase and merge" button only; pull requests with a non-conventional commit fail CI until the commit is reworded. No Terraform, Ansible, secrets, provider, host or client contract changes.
