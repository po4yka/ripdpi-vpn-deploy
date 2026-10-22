# clients/payload-aware-failover Specification

## Purpose
Deliver an explicit usable-data failover contract consumed by the supported recipient runtime.
## Requirements
### Requirement: REQ-FAILOVER-POLICY — Deliver complete supported policy

Explicit client_payload_failover configuration MUST produce ripdpi.payload_failover
with a version, selector binding, two distinct HTTPS control origins, exact sizes
and SHA256 digests, bounded intervals, deadlines, failure/recovery thresholds,
cooldown and maximum backoff. All contributing hosts MUST agree on the policy.
Absent configuration MUST remain absent rather than inventing public endpoints.
Official sing-box artifacts MUST retain only supported engine fields and MUST
NOT claim that their HEAD-based urltest verifies payload transfer.

#### Scenario: Invalid or conflicting policy

- **WHEN** supplied policy is malformed, unbounded, lacks independent origins or differs between hosts
- **THEN** recipient generation refuses before publication without printing inputs

#### Scenario: Supported policy reaches the consumer

- **WHEN** the matching RIPDPI client imports an emitted configured bundle
- **THEN** its persisted selector policy retains every validated field and controls real probing

### Requirement: REQ-FAILOVER-SELECTION — Use bounded verified encrypted paths

The coordinated recipient MUST verify exact body length and digest through each
candidate's actual encrypted path, accepting either independent control target.
It MUST require consecutive failures and recovery, retain cooldown, bound
exponential retries, and reset stale observations after network changes. It MUST
retain an encrypted selection if all candidates fail and never select direct.

#### Scenario: Small responses pass but useful data fails

- **WHEN** the selected candidate cannot deliver the required payload and another candidate repeatedly succeeds
- **THEN** the runtime switches through its existing selector lifecycle after the configured thresholds

#### Scenario: Every candidate fails or one control target is unavailable

- **WHEN** no candidate has qualified recovery evidence
- **THEN** the encrypted selection remains and retries stay bounded
- **AND** failure of one control alone cannot disqualify a path that verifies the other
