## Purpose

Under rebase-only merging the committed lifecycle commits of a task reach
`main` unchanged, so the task contract requires separate commits per
transition but no longer requires separate pull requests or a protected-ref
check before done closure.

## ADDED Requirements

### Requirement: REQ-CIC-1793457997498773-001 — lifecycle transitions stay separate commits and may share a pull request

The task contract MUST accept a review snapshot, a terminal `done` or
`dropped` record and a `close purge` deletion that arrive in one pull request
as separate commits, and MUST continue to reject a single commit that collapses
two of those transitions. `close prepare --outcome done` MUST keep requiring the
selected task record committed in `HEAD` with `status: review`, and MUST NOT
require the snapshot to be present on any remote ref.

#### Scenario: One pull request carries the whole lifecycle

- **GIVEN** a branch with separate commits for the review snapshot, the archive plus terminal record, and the purge deletion
- **WHEN** the branch is rebase-merged and `main` is validated
- **THEN** the purge audit resolves `doing -> review -> done -> deleted` through the first-parent history

#### Scenario: Locally squashed transitions are still rejected

- **GIVEN** a branch whose single commit both creates the review snapshot and records `done`
- **WHEN** the deletion is validated against `main`
- **THEN** the audit rejects the `doing -> done` transition as before

#### Scenario: Done closure without a remote ref

- **GIVEN** a checkout with no `origin/main` ref and the task committed in `review` in `HEAD`
- **WHEN** done closure is prepared
- **THEN** the terminal record and close receipt are prepared

## REMOVED Requirements

### Requirement: REQ-CIC-1793437852879654-001 — require the review snapshot on the protected ref before done closure

**Reason**: Rebase-only merging preserves the committed review snapshot as its own first-parent commit; the protected-ref check only guarded against squash merges.

**Migration**: Remove `--protected-ref` from `close prepare` and `verify`; the `HEAD` committed-review check remains.

### Requirement: REQ-CIC-1793437852879654-002 — report the protected-ref prerequisite from archive-ready verification

**Reason**: Same as above; `verify --archive-ready` keeps its content checks.

**Migration**: None beyond removing the flag.

### Requirement: REQ-CIC-1793437852879654-003 — fail closed on a missing protected ref without fetching

**Reason**: No protected-ref lookup remains.

**Migration**: None.
