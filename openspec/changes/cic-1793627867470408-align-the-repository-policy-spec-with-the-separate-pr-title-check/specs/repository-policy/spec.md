## Purpose

Keep the repository merge policy accurate after the PR title and commit-subject
check moved into its own workflow, so that a title edit reruns only that check
and its result still blocks merges as a branch-required context.

## MODIFIED Requirements

### Requirement: REQ-RPOL-LAYERS — Separate integrity from CI

The repository MUST enforce PRs, linear history, resolved review threads, no force pushes, and no branch deletion without bypass actors. A separate CI ruleset MUST require `required checks`, both CodeQL contexts, and `PR title` from GitHub Actions, strict branch freshness, and only the repository owner as a PR-only bypass actor.

#### Scenario: Owner merges before CI completes

- **WHEN** the owner selects the CI bypass on a resolved pull request
- **THEN** the CI exception is permitted and integrity requirements still apply.

#### Scenario: Other actors or direct pushes

- **WHEN** another actor bypasses CI or the owner pushes directly
- **THEN** the relevant rules remain enforced.

#### Scenario: Same-named context from another app

- **WHEN** an app other than GitHub Actions reports a `PR title` or `required checks` result
- **THEN** that result does not satisfy the CI ruleset.

### Requirement: REQ-RPOL-MERGE — Rebase-only merges with validated commit subjects

The repository MUST allow only rebase merging, keep linear history, remove
merged head branches automatically, and validate in read-only CI that the PR
title and every commit subject in the pull request range are Conventional
Commits without a trailing period, without `Co-authored-by` trailers in the
commit message, and without Codex metadata. The validation MUST run in its own
workflow when a pull request is opened, synchronized, reopened or edited, and
its result MUST be the branch-required `PR title` context. A title or
description edit MUST NOT cancel or restart the complete CI plan for an
unchanged head commit.

#### Scenario: Invalid or edited title

- **WHEN** a PR title is invalid or edited
- **THEN** only the title check runs again and rejects invalid subjects
- **AND** the CI plan already running for the same head commit continues.

#### Scenario: Non-conventional commit inside the pull request

- **GIVEN** a pull request whose commits include one with a non-conventional subject or a `Co-authored-by` trailer
- **WHEN** a new head commit is pushed
- **THEN** the commit check fails naming the offending commit
- **AND** the `PR title` context blocks the merge until the commit is reworded

#### Scenario: Rebase merge preserves commits

- **GIVEN** a pull request with several validated commits
- **WHEN** it is merged
- **THEN** only "Rebase and merge" is offered and each commit becomes its own first-parent commit on `main`
