## Purpose

Define recurring multi-vantage evidence that separates server health from
filtered client-path behavior for every supported deployment profile.

## ADDED Requirements

### Requirement: REQ-MON-1786299441667649-001 — Every profile has independent path evidence

The liveness gate MUST evaluate every supported logical profile through an
unfiltered control and at least two independent filtered access-path classes.

#### Scenario: One profile lacks filtered evidence

- **GIVEN** healthy server-side and unfiltered results
- **WHEN** a required filtered path has no fresh result
- **THEN** the profile MUST remain unknown rather than passing the fleet gate

### Requirement: REQ-MON-1786299441667649-002 — Failure classes remain distinct

The evaluator MUST distinguish server failure, filtered-path failure, unknown,
and stale evidence and MUST NOT infer one class from another.

#### Scenario: Control and filtered outcomes diverge

- **GIVEN** a passing control and a failing filtered path
- **WHEN** evaluation completes
- **THEN** the result MUST identify a path-specific failure without blaming server configuration

### Requirement: REQ-MON-1786299441667649-003 — Rotation remains sustained and operator controlled

Rotation candidacy MUST require fresh sustained quorum evidence, and promotion
MUST remain an explicit operator action after revalidation.

#### Scenario: A single vantage fails once

- **GIVEN** one isolated failed observation
- **WHEN** the evaluator updates fleet state
- **THEN** it MUST NOT create a promotable rotation decision

### Requirement: REQ-MON-1786299441667649-004 — Recurring evidence is redacted and observable

The system MUST retain categorical, freshness-bound evidence for failure,
recovery, and unavailable-vantage transitions without storing live endpoints or credentials.

#### Scenario: A vantage becomes unavailable

- **GIVEN** a previously healthy recurring schedule
- **WHEN** one required vantage cannot be queried
- **THEN** state MUST become explicitly unavailable or unknown and alert once without leaking connection data
