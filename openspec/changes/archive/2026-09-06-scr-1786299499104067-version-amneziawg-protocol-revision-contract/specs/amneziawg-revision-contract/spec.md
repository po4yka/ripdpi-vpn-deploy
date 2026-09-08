## Purpose

Define an explicit, fail-closed wire-revision boundary for AmneziaWG profiles
shared by deployment emitters and the RIPDPI client.

## ADDED Requirements

### Requirement: REQ-SCR-1786299499104067-001 — AWG entries declare wire revision

Every emitted AWG entry MUST declare a supported wire revision and immutable
implementation provenance sufficient for compatibility validation.

#### Scenario: Current revision is emitted

- **GIVEN** a current supported AWG deployment
- **WHEN** its client bundle is rendered
- **THEN** the entry MUST identify the current wire revision and pinned implementation source

### Requirement: REQ-SCR-1786299499104067-002 — Unknown revisions fail closed

The schema and validators MUST reject an unknown, missing, or inconsistent wire
revision before the profile is eligible for activation.

#### Scenario: A later revision reaches an older validator

- **GIVEN** an AWG entry with an unsupported revision
- **WHEN** bundle validation runs
- **THEN** validation MUST fail with a typed compatibility result and no fallback interpretation

### Requirement: REQ-SCR-1786299499104067-003 — Fingerprints are revision bound

The profile fingerprint MUST include the declared revision so equal-looking
parameters from different wire contracts cannot share an identity.

#### Scenario: Revision changes without parameter changes

- **GIVEN** two entries with identical visible parameters and different revisions
- **WHEN** their fingerprints are computed
- **THEN** the fingerprints MUST differ and cross-revision substitution MUST be rejected

### Requirement: REQ-SCR-1786299499104067-004 — Later revisions remain staging only

A revision newer than the current production contract MUST require an explicit
staging cohort and MUST NOT become a production default through source updates.

#### Scenario: Source watcher detects a new revision

- **GIVEN** a new upstream revision or release claim
- **WHEN** automation updates its observation state
- **THEN** production emission MUST remain unchanged until cross-repository staging acceptance is recorded
