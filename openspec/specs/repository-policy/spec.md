# repository-policy Specification

## Purpose
Keep repository changes reviewable while permitting the owner to bypass CI through a pull request and preserving release identities.

## Requirements

### Requirement: REQ-RPOL-LAYERS — Separate integrity from CI

The repository MUST enforce PRs, linear history, resolved review threads, no force pushes, and no branch deletion without bypass actors. A separate CI ruleset MUST require `required checks` and both CodeQL contexts from GitHub Actions, strict branch freshness, and only the repository owner as a PR-only bypass actor.

#### Scenario: Owner merges before CI completes

- **WHEN** the owner selects the CI bypass on a resolved pull request
- **THEN** the CI exception is permitted and integrity requirements still apply.

#### Scenario: Other actors or direct pushes

- **WHEN** another actor bypasses CI or the owner pushes directly
- **THEN** the relevant rules remain enforced.

### Requirement: REQ-RPOL-APPLY — Reviewed and verified configuration

Configuration MUST default to a read-only plan, refuse a foreign repository or owner identity, preserve unrelated rulesets, install integrity rules before narrowing the existing rule, and verify remote settings after writes. The old classic-protection workflow MUST be removed. Failures MUST exit nonzero without claiming completion.

#### Scenario: Partial failure and retry

- **WHEN** a remote write fails after an earlier rule succeeds
- **THEN** the command fails and a new plan reads the actual state before a retry.

#### Scenario: Existing policy matches

- **WHEN** all managed remote rules and settings match the configuration
- **THEN** apply performs no writes.

#### Scenario: Recovery or incompatible classic rule

- **WHEN** classic branch protection remains or a configuration identity is invalid
- **THEN** configuration refuses before mutation and requires explicit operator reconciliation.

### Requirement: REQ-RPOL-RELEASE — Stable release identities

Release tags matching `vpnd-v*` MUST reject updates and deletion without bypass actors. Future published releases MUST be immutable. Draft assets MUST remain replaceable until publication. Recovery after publication MUST use a new version, not replace published assets.

#### Scenario: Draft becomes published

- **WHEN** all draft assets are uploaded and the release is published
- **THEN** its assets and tag become immutable; tag creation remains available to release automation.

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

### Requirement: REQ-RPOL-DEPS — Complete update coverage

Dependabot MUST cover all provider roots, root and vpnd Python manifests, tasking npm, Actions, and the Go helper with weekly grouped updates and the existing cooldown.

#### Scenario: Routine dependency release

- **WHEN** a supported dependency has a new version
- **THEN** its configured ecosystem can propose an update after the cooldown without bypassing CI or human merge control.
