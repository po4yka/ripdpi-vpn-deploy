## Purpose

Keep terminal task closure auditable by requiring a durable reviewed
predecessor and by documenting an operator sequence that cannot archive a
change before that predecessor is committed.

## ADDED Requirements

### Requirement: REQ-CIC-1788741692326070-001 — require committed review before done closure

`taskctl close prepare --outcome done` MUST accept a task only when the selected
task record already exists at its current repository path in `HEAD`, carries
the same task ID, and has `status: review` in that committed snapshot.

#### Scenario: Working-tree-only review transition is refused

- **GIVEN** `HEAD` contains the selected task in a non-review state
- **AND** the working tree changes that task to `review`
- **WHEN** done closure is prepared
- **THEN** the command fails before changing the issue or creating a close receipt

#### Scenario: Committed review proceeds to terminal preparation

- **GIVEN** the selected task and completed execution are committed in `review`
- **WHEN** all applicable verification and archive-readiness checks pass
- **THEN** done closure prepares the existing terminal record and receipt
- **AND** purge remains a later separately committed operation

#### Scenario: Selected task path or identity differs from HEAD

- **GIVEN** the working task is uncommitted at a new path or its committed record names another ID
- **WHEN** done closure is prepared
- **THEN** the command fails before any lifecycle artifact is mutated

### Requirement: REQ-CIC-1788741692326070-002 — keep the archive workflow executable

The canonical OpenSpec archive workflow MUST require the portfolio task and
completed execution to be committed in `review` before archive readiness,
OpenSpec archival, or done closure, and MUST retain a separate terminal-state
commit before purge.

#### Scenario: Operator finalizes an OpenSpec change

- **GIVEN** implementation and required evidence are complete
- **WHEN** the canonical archive workflow is followed
- **THEN** the operator commits the review state before running the archive command
- **AND** `close prepare --outcome done` observes that committed review snapshot

### Requirement: REQ-CIC-1788741692326070-003 — bound the committed-review lookup

The committed-review guard MUST read the selected task record directly from
`HEAD` and MUST NOT perform one historical task-record read for every other
active portfolio task.

#### Scenario: Portfolio size grows independently of the selected close

- **GIVEN** one reviewed task and multiple unrelated active task records
- **WHEN** the committed-review guard checks the selected task
- **THEN** it reads exactly that selected `HEAD` record
- **AND** no repository-wide issue-tree scan is performed for this guard

### Requirement: REQ-CIC-1788741692326070-004 — scope evidence history to OpenSpec ownership

Historical evidence-transfer validation MUST require verification records only
for task snapshots whose own `spec_mode` is `required`, and MUST retain all
required snapshots when task mode or OpenSpec change identity later changes.

#### Scenario: Existing simple-work task adopts OpenSpec

- **GIVEN** a published task has earlier `spec_mode: not-required` snapshots
  without OpenSpec verification files
- **WHEN** that task adopts OpenSpec and archive readiness validates its evidence history
- **THEN** the pre-OpenSpec snapshots do not require a fabricated verification record
- **AND** every subsequent required snapshot remains subject to evidence-transfer validation
