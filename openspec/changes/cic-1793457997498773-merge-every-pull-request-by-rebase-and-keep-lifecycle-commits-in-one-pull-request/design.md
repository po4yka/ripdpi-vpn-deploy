## Context

`.github/repository-policy.json` is the source of truth for repository
settings and rulesets; `scripts/configure-repository.py` plans and applies it
through the GitHub API and `tests/unit/test_branch_protection_contract.py`
pins its content. The `PR title` CI job runs `scripts/check-pr-title.py`
against the pull-request event with a shallow checkout. `taskctl` proves
lifecycle transitions from first-parent history (`validate_deleted_history`,
`resolve_terminal_task`) and, since `CIC-1793437852879654`, refuses done
closure until the review snapshot is on `origin/main`. REQ-RPOL-MERGE in the
active `repository-rulesets` change states squash-only merging.

## Goals / Non-Goals

- Goal: one pull request per task lifecycle without weakening the history proof.
- Goal: every commit that reaches `main` is a validated Conventional Commit without co-author trailers, because rebase merges feed release-please commit by commit.
- Non-goal: changing the purge audit, the committed-review policy, or `close purge`.
- Non-goal: applying the policy to GitHub inside this change; `make repository-policy-apply` is a separate authorized action after review.
- Non-goal: changing release-please configuration.

## Decisions

- Rebase-only, not "rebase alongside squash": with both allowed, a squash on a lifecycle pull request would silently reintroduce the collapsed history and the failure would surface only at purge. Rejected: merge commits, which would drop `required_linear_history` and change every history-walking tool.
- Settings drop `squash_merge_commit_title` and `squash_merge_commit_message`: they only apply to squash merges and the configuration command compares exactly the keys present in `settings`.
- `scripts/check-pr-title.py` keeps its name and the title check (the title still names the pull request and CI edits re-trigger it) and additionally reads `pull_request.base.sha..pull_request.head.sha` with `git log --format=%H%x00%s%x00%b%x1e` and applies `valid()` to each subject plus a `Co-authored-by` trailer check on each body. The job checkout gets `fetch-depth: 0` so the range is available; permissions stay read-only. Rejected: a separate script and job, which would add a required-check row for the same contract.
- The gate from `CIC-1793437852879654` is removed outright rather than disabled: `require_committed_review` keeps the `HEAD` check, `DEFAULT_PROTECTED_REF`, `require_review_on_protected_ref`, the `--protected-ref` arguments and their tests go, and the test fixture stops maintaining `refs/remotes/origin/main`. Rejected: keeping the flag as an opt-in, which is dead code once the policy is rebase-only.
- REQ-RPOL-MERGE is modified through a delta instead of editing the `repository-rulesets` artifacts, so ownership stays with each task; this change archives after `repository-rulesets` so the MODIFIED delta applies to a main spec that contains the requirement.
- Lifecycle documentation keeps "separate commits" as the invariant and drops "separate pull requests"; it adds "never squash lifecycle commits locally".

## Contracts and ownership

- Repository policy: `.github/repository-policy.json`, `tests/unit/test_branch_protection_contract.py`, `docs/how-to/branch-protection.md`.
- CI: `.github/workflows/ci.yml` (`pr-title` job), `scripts/check-pr-title.py`, `tests/unit/test_pr_title.py`, `docs/reference/testing.md`.
- Tasking: `scripts/tasks/taskctl.py`, `scripts/tests/test_taskctl.py`, `docs/tasks/README.md`, `.agents/skills/openspec-archive-change/SKILL.md`, `.agents/skills/repo-task-board/SKILL.md`, `tools/tasking/generated-assets.lock.json`, `CONTRIBUTING.md`.
- No Terraform, Ansible, secrets, vpnd or client contract is affected.

## Risks / Trade-offs

- Pull requests with sloppy intermediate commits now fail CI → the message names the commit; authors reword with an interactive rebase on their own branch before merge.
- `Co-authored-by` trailers, previously added by GitHub to squash messages, are now rejected in commits → consistent with the repository rule that forbids them.
- Until `make repository-policy-apply` runs, GitHub still squashes; this change's own pull request is therefore a single commit.
- Archive ordering: this change's MODIFIED delta requires REQ-RPOL-MERGE in the main spec, which the `repository-rulesets` archive provides → noted in the proposal; `taskctl openspec archive` fails closed if attempted earlier.

## Migration Plan

Forward: merge this change (as one commit), then run the authorized `make repository-policy-plan` and `make repository-policy-apply`; from then on merge with "Rebase and merge" only. Rollback: revert the commit and re-apply the previous policy JSON through the same command. No provider, schema or runtime rollout gates apply.
