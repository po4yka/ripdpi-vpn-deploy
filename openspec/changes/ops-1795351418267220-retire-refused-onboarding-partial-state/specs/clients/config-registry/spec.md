## ADDED Requirements

### Requirement: REQ-REGISTRY-REFUSED-ONBOARDING — Retire an exact refused-onboarding prefix

Unbound staging retirement MUST accept, besides all-absent onboarding outputs, only the prefix that promotion finalization writes before installation: authority, then liveness config, then executor manifest copy. Each present output MUST be exactly what the retained intent produces. Retirement MUST NOT create a binding, MUST retain the accepted outputs, and MUST bind their digests into the journaled request.

#### Scenario: Refused finalization prefix retires

- **GIVEN** verified provider absence, empty state and an issued unbound client
- **AND** finalization left an authority with exactly `schema_version` 1, a 64-hex `scope_sha256` and a positive integer `applied_at`, the intent's liveness config with that `applied_at`, and the original executor manifest bytes
- **WHEN** the operator runs `make retire-unbound-staging-client` and then `make retire-unbound-staging-executor`
- **THEN** the client and the prepared executor are retired
- **AND** the partial outputs remain unchanged and their digests are in the journaled request

#### Scenario: Changed partial output refuses resume

- **WHEN** a retained partial output is changed after the journal recorded the request
- **THEN** the resumed retirement refuses with `retirement-bound`
- **AND** removing only the last retained output refuses resume with `retirement-journal`

### Requirement: REQ-REGISTRY-PARTIAL-FOREIGN — Refuse other partial onboarding state

Unbound staging retirement MUST refuse with `retirement-bound`, before any journal or encrypted mutation, when a binding, registry, pending registry or promotion config output or a profile assignment record exists, when the prefix has a gap, or when a present output differs from what the intent produces.

#### Scenario: Foreign partial state refuses

- **WHEN** a partial output has a different epoch or manifest, an authority outside its exact shape, a gap in the write order, or a binding, registry, pending registry, promotion config or profile assignment record is present
- **THEN** retirement refuses with `retirement-bound` without a journal or SOPS change
