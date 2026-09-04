## Purpose

Keep repository-owned GitHub Actions read-only by default while granting each
publishing job only the write capabilities required for its observable output.

## ADDED Requirements

### Requirement: REQ-WORKFLOW-TOKEN-SCOPE — Scope write permissions to the consuming job

Each repository-owned Molecule image publication workflow MUST declare
read-only permissions at the top level. A job MAY request a named write
permission only when that job performs the corresponding publication, and
unrelated or future jobs in those workflows MUST inherit no write authority.

#### Scenario: Molecule image workflow publishes and scans an image

- **WHEN** either repository-owned Molecule image publication workflow runs on an authorized push or manual dispatch
- **THEN** its publishing job has `packages: write` and `security-events: write`, the workflow top level remains read-only, and image publication plus SARIF upload retain their existing behavior

#### Scenario: A new job is added to an image workflow

- **WHEN** a job is added without an explicit permission override
- **THEN** it inherits read-only repository access and cannot publish packages or security events

#### Scenario: Hosted Scorecard analyzes the exact implementation SHA

- **WHEN** Scorecard evaluates the final implementation SHA
- **THEN** alerts 341 through 344 are absent without dismissal or repository-wide permission expansion
