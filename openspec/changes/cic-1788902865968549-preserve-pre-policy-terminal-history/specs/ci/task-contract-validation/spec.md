## Purpose

Keep committed terminal task history valid under the contract that existed at
the time while making committed-review policy activation monotonic and
non-bypassable for every later terminal transition.

## ADDED Requirements

### Requirement: REQ-CIC-1788902865968549-001 — version committed-review history enforcement

The task validator MUST determine whether committed-review enforcement was
activated anywhere in the first-parent project-config ancestry of the exact
terminal transition and MUST keep that activation effective for all descendant
terminal transitions even if a later config removes or lowers the policy field.

#### Scenario: Pre-activation terminal history remains valid

- **GIVEN** a task reached `done` through a transition accepted before the
  committed-review policy was first activated
- **WHEN** a later policy-aware revision validates or purges that terminal record
- **THEN** the historical transition remains valid
- **AND** current policy is not applied retroactively

#### Scenario: Unversioned peer history remains fail-closed

- **GIVEN** a federation peer has never declared committed-review policy
- **WHEN** its task changes directly from `doing` to `done` and is purged
- **THEN** terminal history validation rejects the transition
- **AND** the malformed peer task cannot satisfy a local blocker

#### Scenario: Pre-activation compatibility is narrow

- **GIVEN** the current checkout proves a terminal revision predates policy
  activation
- **WHEN** the task reaches `done` directly from `todo`, `blocked`, or no prior
  state
- **THEN** terminal history validation rejects the transition
- **AND** only the historical `doing` to `done` form receives compatibility

#### Scenario: Post-activation downgrade cannot bypass review

- **GIVEN** committed-review policy version 1 exists in the first-parent
  ancestry of a task's terminal revision
- **AND** a descendant config removes the field or sets it to version 0
- **WHEN** the task changes directly from `doing` to `done`
- **THEN** prospective and committed deletion validation reject the transition
- **AND** restoring version 1 later does not repair the malformed history

#### Scenario: Current committed review path remains accepted

- **GIVEN** policy version 1 is active and the task has a committed `review`
  snapshot
- **WHEN** a later separate commit prepares `done` and another commit purges it
- **THEN** terminal history validation accepts the lifecycle
- **AND** the existing review, receipt, archive, and evidence checks still apply
