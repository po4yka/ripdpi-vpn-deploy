## MODIFIED Requirements

### Requirement: REQ-FAILOVER-POLICY — Deliver complete supported policy

Explicit client_payload_failover configuration MUST produce version 2
ripdpi.payload_failover with a selector binding, two distinct HTTPS control
origins, exact sizes and SHA256 digests, bounded intervals, deadlines,
failure/recovery thresholds, cooldown and maximum backoff. An optional quality
object MUST satisfy the coordinated profile-quality-mtu contract. All
contributing hosts MUST agree on the policy. Absent configuration MUST remain
absent rather than inventing public endpoints. Version 1 MUST be rejected.
Official sing-box artifacts MUST retain only supported engine fields and MUST
NOT claim that their HEAD-based urltest verifies payload transfer.

#### Scenario: Keep policy agreement and engine boundaries

- **WHEN** delivery artifacts consume explicit or absent failover configuration
- **THEN** all contributing hosts MUST agree on the policy
- **AND** absent configuration MUST remain absent rather than inventing public endpoints
- **AND** official sing-box artifacts MUST retain only supported engine fields and MUST NOT claim that HEAD-based urltest verifies payload transfer

#### Scenario: Invalid or conflicting policy

- **WHEN** supplied policy is malformed, obsolete, unbounded, lacks independent origins or differs between hosts
- **THEN** recipient generation refuses before publication without printing inputs

#### Scenario: Supported policy reaches the consumer

- **WHEN** the matching RIPDPI client imports an emitted configured bundle
- **THEN** its persisted selector policy retains every validated field and controls real probing
- **AND** quality absence retains payload-health behavior while explicit quality enables bounded comparison
