## Purpose

Extend the local task contract so evidence ownership remains verifiable after a
completed source task is archived and purged, while every evidence category and
unsafe historical state continues to fail closed.

## ADDED Requirements

### Requirement: REQ-CIC-1788708456909496-001 — resolve durable local evidence links

The task contract MUST allow an active task's non-blocking `related_tasks`
entry to reference a locally purged task only when Git history proves that the
referenced task completed the canonical terminal transition, archive, and purge
lifecycle with outcome `done`.

#### Scenario: Active operational task retains its completed source link

- **GIVEN** a source task has a valid committed `done` snapshot and later purge commit
- **WHEN** an active operational task retains that source ID in `related_tasks`
- **THEN** task validation and graph rendering resolve the historical task as `done`
- **AND** the durable evidence-ownership edge remains visible

#### Scenario: Completed lifecycle is integrated from a merged lane

- **GIVEN** one merged lane contains the source task's complete valid create, terminal, archive, and purge lifecycle
- **WHEN** the integration tree retains an active owner's related edge but no source issue
- **THEN** validation resolves exactly one valid lane-local deletion candidate
- **AND** zero, malformed, stale-only, or multiple candidates fail closed

### Requirement: REQ-CIC-1788708456909496-002 — fail closed on invalid historical targets

The task contract MUST reject a local reference whose target is absent,
`dropped`, uncommitted, purged without a valid terminal snapshot, transitioned
out of terminal state, has an invalid latest reintroduced incarnation, or
otherwise fails the current terminal-history validation contract.

#### Scenario: Historical reference does not prove completed work

- **GIVEN** an active task references a missing, dropped, malformed, or incomplete historical task
- **WHEN** task validation or graph resolution processes that reference
- **THEN** the command fails with the referenced task ID and the invalid state
- **AND** it does not silently remove or treat the reference as satisfied

### Requirement: REQ-CIC-1788708456909496-003 — preserve safe purge boundaries

`taskctl close purge` MUST permit an incoming `related_tasks` edge that can be
resolved through the committed terminal history it is about to create, and MUST
continue to reject an incoming parent edge, unresolved blocker edge, self edge,
or any reference that would leave the active graph invalid.

#### Scenario: Purge a completed source with an evidence owner

- **GIVEN** an active operational task has a non-blocking related edge to a committed done source task
- **WHEN** the source task's archived close receipt is committed and `close purge` runs
- **THEN** only the source issue and canonical execution artifacts are purged
- **AND** the operational task keeps a resolvable historical related edge

#### Scenario: Purge would orphan an unsafe relationship

- **GIVEN** an active task uses the candidate source as its parent or unresolved blocker
- **WHEN** `close purge` runs for the source task
- **THEN** purge fails before deleting any task artifact
- **AND** the active relationship remains unchanged

#### Scenario: Terminal artifacts changed after their commit

- **GIVEN** a terminal issue, execution record, verification, or lifecycle receipt differs from `HEAD`
- **WHEN** `close purge` runs even with a rewritten self-consistent working receipt
- **THEN** purge fails before deleting any artifact
- **AND** every working-tree change remains intact

### Requirement: REQ-CIC-1788708456909496-004 — map shared operational evidence durably

Shared operational evidence MUST discharge a source-task requirement only when
the active operational task retains a task-graph link to that source and both
verification records name the exact requirement ID, acceptance command,
evidence category, and exact source revision covered by the observation.

#### Scenario: Shared observation has a complete mapping

- **GIVEN** one operational run is intended to satisfy requirements from multiple linked source tasks
- **WHEN** closure readiness is evaluated for any source task
- **THEN** every transferred requirement has the same ID, command, category, and source revision in the source and operational verification records
- **AND** a durable task-graph link identifies the operational owner

#### Scenario: Prose delegation lacks a mapping

- **GIVEN** a verification record merely names another task without the required mapping
- **WHEN** closure readiness is evaluated
- **THEN** the original required or blocked evidence remains open
- **AND** the source task cannot be terminally closed

#### Scenario: Historical transfer is checked before archival

- **GIVEN** the transfer policy is active and a committed evidence state changed from `required` or `blocked` to `not_applicable`
- **WHEN** archive readiness, OpenSpec archival, close preparation, or purge is evaluated
- **THEN** the exact reciprocal mapping at the transition revision is validated before mutation
- **AND** a later mapping cannot retroactively authorize the transfer

### Requirement: REQ-CIC-1788708456909496-005 — require evidence at the observed layer

The proportional-verification policy MUST keep local, remote CI, dry-run,
staging, live, client, and artifact evidence distinct. Authenticated client
traffic MUST include `client: passed` evidence in addition to every applicable
staging or live category, and an existing `required` or `blocked` category MUST
NOT become `not_applicable` solely because another task exists.

#### Scenario: Host observation lacks client proof

- **GIVEN** staging or live host checks pass without an authenticated client traffic observation
- **WHEN** a task requires real client connectivity
- **THEN** its client evidence remains required or blocked
- **AND** source, host, fixture, or CI evidence cannot close that client requirement

#### Scenario: Requirement ownership moves before closure

- **GIVEN** a source task currently owns required or blocked operational evidence
- **WHEN** maintainers want a linked operational task to own the evidence instead
- **THEN** an OpenSpec update first moves and maps the requirement under REQ-CIC-1788708456909496-004
- **AND** the source record is not reclassified by an evidence-only edit

#### Scenario: Policy activation preserves legacy classifications

- **GIVEN** an evidence category was already `not_applicable` before the transfer policy activated
- **WHEN** policy activation leaves that category unchanged
- **THEN** archive readiness does not require a retroactive mapping
- **BUT** a `required` or `blocked` to `not_applicable` transition in the activation commit is rejected
