## Purpose

Qualify an experimental fallback without exposing account material or confusing synthetic compatibility with real path effectiveness.

## ADDED Requirements

### Requirement: REQ-SFR-REVIEW — Versioned admission review

The qualification MUST pin and review source revisions, license obligations, client interoperability and threat boundaries. Unknown results MUST block admission. The report MUST name each client it exercised by implementation, revision and platform. The upstream reference client proves protocol compatibility only; RIPDPI client support stays unclaimed until a peer task in the client repository exercises it.

#### Scenario: Unsupported client

- **WHEN** the chosen client cannot interoperate with the reviewed runtime
- **THEN** the report rejects admission and no bundle field or default changes.

### Requirement: REQ-SFR-FIXTURE — Isolated failure qualification

The harness MUST use the exact pinned candidate client/server against local synthetic fixtures with no real accounts, secrets or external services. It MUST reject substitute candidate mocks as evidence and block qualification if isolation needs material protocol rewriting.

#### Scenario: Lifecycle and resource failures

- **WHEN** sessions expire, peers disconnect, frames are lost or reordered, or quotas and buffers reach their limits
- **THEN** the fixture records bounded failure, integrity and cleanup evidence without exposing account material, and the report reviews confidentiality separately from obfuscation.

#### Scenario: Fixture requests external access

- **WHEN** a test attempts to use a non-fixture address or account material
- **THEN** execution stops before contact and reports an authorization boundary rather than a passing test.

### Requirement: REQ-SFR-DECISION — Explicit evidence and rollback

The report MUST record measured payload delivery, bounded failure behavior, cleanup, confidentiality gaps, latency and resource cost, comparing to the unchanged baseline. It MUST distinguish synthetic results from separately authorized path measurements and permit a reject outcome.

#### Scenario: Control channel works but payload fails

- **WHEN** session setup succeeds but controlled application bytes are not delivered intact within the budget
- **THEN** the result is failure, not successful circumvention, and all fixture resources are cleaned up.
