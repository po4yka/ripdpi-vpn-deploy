## Purpose

Extend the committed-review prerequisite so that done closure can only be
prepared after the review snapshot has reached the protected integration
branch, keeping the first-parent history of `main` valid for the later purge
audit under a squash-only merge policy.

## ADDED Requirements

### Requirement: REQ-CIC-1793437852879654-001 — require the review snapshot on the protected ref before done closure

`taskctl close prepare --outcome done` MUST accept a task only when the
selected task record exists at its current repository path in the protected
ref, carries the same task ID, and has `status: review` in that snapshot, in
addition to the existing `HEAD` committed-review check. The protected ref
defaults to `origin/main` and MAY be overridden with `--protected-ref <ref>`.

#### Scenario: Review snapshot exists only in local branch history

- **GIVEN** `HEAD` contains the selected task in `review`
- **AND** the protected ref contains the task in `doing` or does not contain the task at its current path
- **WHEN** done closure is prepared
- **THEN** the command fails before changing the issue or creating a close receipt
- **AND** the message names the task ID, the protected ref, and that the review snapshot must be merged as its own pull request or fetched before done closure

#### Scenario: Review snapshot is on the protected ref

- **GIVEN** the protected ref contains the selected task at its current path with the same ID in `review`
- **AND** every existing committed-review, verification and archive-readiness check passes
- **WHEN** done closure is prepared
- **THEN** the terminal record and close receipt are prepared as before

#### Scenario: Protected ref names another task at the selected path

- **GIVEN** the protected ref holds a record with a different task ID at the selected path
- **WHEN** done closure is prepared
- **THEN** the command fails before any lifecycle artifact is mutated

#### Scenario: Dropped closure is unaffected

- **GIVEN** a task is prepared with `--outcome dropped`
- **WHEN** the protected ref lacks the task or holds it in a non-review state
- **THEN** the protected-ref check is not applied and existing dropped-closure rules decide

### Requirement: REQ-CIC-1793437852879654-002 — report the protected-ref prerequisite from archive-ready verification

`taskctl verify <id> --archive-ready` MUST fail with the same protected-ref
refusal as done closure when the selected task record on the protected ref is
absent, names another task ID, or is not in `status: review`, so the archive
workflow stops before `taskctl openspec archive`.

#### Scenario: Archive-ready verification before the review pull request merges

- **GIVEN** the selected task is committed in `review` in `HEAD` but not present in `review` on the protected ref
- **WHEN** `verify <id> --archive-ready` runs
- **THEN** the command fails with the protected-ref message
- **AND** `verify <id>` without `--archive-ready` is unaffected

#### Scenario: Internal archive-readiness checks keep their scope

- **GIVEN** `taskctl openspec archive` runs its internal archive-readiness verification for a dropped task
- **WHEN** the protected ref lacks a review snapshot for that task
- **THEN** the dropped archive proceeds under the existing dropped-task rules

### Requirement: REQ-CIC-1793437852879654-003 — fail closed on a missing protected ref without fetching

When the protected ref cannot be resolved in the current repository, done
closure and archive-ready verification MUST fail with a message that names the
ref and the `--protected-ref` override. `taskctl` MUST NOT fetch, create or
move any ref.

#### Scenario: Checkout without the default protected ref

- **GIVEN** the repository has no `origin/main` ref and no `--protected-ref` was given
- **WHEN** done closure or archive-ready verification runs
- **THEN** the command fails naming `origin/main` and `--protected-ref`
- **AND** no network operation is attempted and no lifecycle artifact is written

#### Scenario: Explicit protected ref override

- **GIVEN** `--protected-ref <ref>` names a resolvable ref that holds the selected task in `review`
- **WHEN** done closure or archive-ready verification runs
- **THEN** the check evaluates that ref instead of `origin/main`
