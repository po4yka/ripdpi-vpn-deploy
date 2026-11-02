## Purpose

Deliver a bounded XHTTP connection pool through the complete supported recipient path.

## ADDED Requirements

### Requirement: REQ-XHTTP-RECIPIENT-POOL — Preserve the bounded endpoint pool

The producer and paired RIPDPI consumer MUST preserve the typed stream-up pool
with an integer connection limit from 1 through 4 and zero request, age and reuse
retirement limits. Sessions for one endpoint MUST share that pool. Unknown fields,
invalid bounds, unsupported modes and nonzero retirement limits MUST refuse.

#### Scenario: Primary and alternate retain their pools

- **WHEN** a selected device imports the emitted bounded stream-up profile
- **THEN** primary and alternate identities retain their complete tuning through storage and runtime
- **AND** concurrent sessions do not create more carriers than the endpoint limit

#### Scenario: Invalid tuning preserves accepted state

- **WHEN** a profile has unsupported mode, unknown fields or invalid pool limits
- **THEN** producer or consumer admission refuses without replacing the accepted profile

#### Scenario: Pool shutdown and rollback

- **WHEN** the endpoint runtime stops or the operator restores the untuned profile
- **THEN** owned pooled connections are released and the normal untuned path remains usable
