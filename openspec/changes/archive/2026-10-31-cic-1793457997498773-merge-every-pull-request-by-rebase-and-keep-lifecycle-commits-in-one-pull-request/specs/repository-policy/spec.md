## Purpose

Keep `main` linear through rebase-only merges so that every pull-request commit
lands unchanged as its own first-parent commit, and validate each of those
commits before it can become a release-please input.

## RENAMED Requirements

- FROM: `### Requirement: REQ-RPOL-MERGE — Consistent squash subjects`
- TO: `### Requirement: REQ-RPOL-MERGE — Rebase-only merges with validated commit subjects`

## MODIFIED Requirements

### Requirement: REQ-RPOL-MERGE — Rebase-only merges with validated commit subjects

The repository MUST allow only rebase merging, keep linear history, remove
merged head branches automatically, and validate in read-only CI that the PR
title and every commit subject in the pull request range are Conventional
Commits without a trailing period, without `Co-authored-by` trailers in the
commit message, and without Codex metadata. The validation result MUST reach
the required CI aggregate.

#### Scenario: Invalid or edited title

- **WHEN** a PR title is invalid or edited
- **THEN** the title check runs and rejects invalid subjects.

#### Scenario: Non-conventional commit inside the pull request

- **GIVEN** a pull request whose commits include one with a non-conventional subject or a `Co-authored-by` trailer
- **WHEN** CI validates the pull request
- **THEN** the commit check fails naming the offending commit
- **AND** the required aggregate fails until the commit is reworded

#### Scenario: Rebase merge preserves commits

- **GIVEN** a pull request with several validated commits
- **WHEN** it is merged
- **THEN** only "Rebase and merge" is offered and each commit becomes its own first-parent commit on `main`
