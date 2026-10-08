# Spec merge examples

## Delta format

A delta introducing a capability can supply Purpose. Existing main Purpose
remains authoritative. Operation headers describe edits to the main spec:

```markdown
## Purpose

Describe the new capability's behavior and reason for existing.

## ADDED Requirements

### Requirement: REQ-INPUT-VALIDATION — Input validation
The system SHALL validate the requested input.

#### Scenario: Valid input
- **WHEN** the input meets the contract
- **THEN** the system accepts it

## MODIFIED Requirements

### Requirement: REQ-EXISTING-BEHAVIOR — Existing behavior
The system SHALL retain its existing behavior and handle the new case.

#### Scenario: Existing case
- **WHEN** the existing case occurs
- **THEN** the system retains its existing result

#### Scenario: New case
- **WHEN** the new case occurs
- **THEN** the system returns the specified result

## REMOVED Requirements

### Requirement: REQ-SUPERSEDED-BEHAVIOR — Superseded behavior

## RENAMED Requirements

- FROM: `### Requirement: REQ-NAMED-BEHAVIOR — Old name`
- TO: `### Requirement: REQ-NAMED-BEHAVIOR — New name`
```

The MODIFIED block includes every scenario that survives; a new scenario alone
is not the complete delta. Preserve other requirements and unmentioned content
in their existing order.

## Main format

Merge operation contents under one Requirements section, removing the operation
headers. Never copy the delta file over the main spec:

```markdown
# Input validation Specification

## Purpose
Describe what the capability does and why it exists.

## Requirements

### Requirement: REQ-INPUT-VALIDATION — Input validation
The system SHALL validate the requested input.

#### Scenario: Valid input
- **WHEN** the input meets the contract
- **THEN** the system accepts it
```

## Nested selection

For a selected absolute delta entry ending in
`/specs/billing/invoices/spec.md`, retain `billing/invoices` as the capability
path. Resolve its main file under the status response's `planningHome.root`:
`<planningHome.root>/openspec/specs/billing/invoices/spec.md`.
An explicit selection of that complete entry excludes other returned deltas;
reading or fetching instructions does not widen the selection.
