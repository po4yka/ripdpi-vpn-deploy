## Purpose

Define safe cross-provider redundancy and explicit promotion for one critical
logical deployment profile without automatic route mutation.

## ADDED Requirements

### Requirement: REQ-OPS-1786299564848189-001 — Critical profile has an independent spare

The fleet MUST support an active and warm-spare instance of one critical
logical profile on different provider failure domains.

#### Scenario: Active provider is unavailable

- **GIVEN** a converged active profile and a separately converged healthy spare
- **WHEN** the active provider becomes unreachable
- **THEN** the spare MUST remain independently reachable and evaluable

### Requirement: REQ-OPS-1786299564848189-002 — State and credentials remain isolated

Active and spare instances MUST derive from the same reviewed source while
retaining separate Terraform state, credentials, and evidence identities.

#### Scenario: Spare is reconciled

- **GIVEN** a reviewed source revision
- **WHEN** both environments are planned and converged
- **THEN** no state, secret, client identity, or evidence record MAY be shared accidentally

### Requirement: REQ-OPS-1786299564848189-003 — Promotion fails closed

Promotion MUST require sustained multi-vantage profile failure, a healthy spare,
matching configuration identity, and explicit operator confirmation.

#### Scenario: Evidence is indeterminate or stale

- **GIVEN** a failed active path and incomplete or stale spare evidence
- **WHEN** promotion is evaluated
- **THEN** promotion MUST be refused and the active binding MUST remain unchanged

### Requirement: REQ-OPS-1786299564848189-004 — Rollback is rehearsed before production use

The system MUST support a staging promotion and rollback drill with deterministic
cleanup before the spare can be used for production decisions.

#### Scenario: Staging promotion is reverted

- **GIVEN** a healthy staging active/spare pair
- **WHEN** promotion and rollback are exercised
- **THEN** the original binding MUST be restored and temporary state MUST be removed
