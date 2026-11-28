## ADDED Requirements

### Requirement: REQ-AUDIT-SOURCE — Source-bound policy enforcement

Policy bans MUST use the Xray access-log source address. Approved management addresses and Tailnet address ranges MUST be exempt. Approved Tailnet SSH MUST remain reachable if an offender set already contains its source.

#### Scenario: Supported source formats

- **WHEN** Xray records a supported IPv4 or IPv6 source on a policy event
- **THEN** the limiter counts a canonical non-exempt source and ignores events without a valid source.

### Requirement: REQ-AUDIT-PRIVATE-PLAN — Confidential runtime candidates

Ansible MUST suppress output for every update to the complete transport candidate plan.

#### Scenario: Candidate accumulation

- **WHEN** a later role adds an artifact to a plan that contains a private configuration
- **THEN** callback output does not contain the candidate values.

### Requirement: REQ-AUDIT-SECRET-INPUT — Explicit credential and obfuscation inputs

Strict validation MUST reject public placeholders, invalid string endpoints and noninteger values in integer fields. Rotation and ingest MUST reject placeholders as usable cohort tokens. The Hysteria server and client MUST require a nonempty password when Salamander is enabled.

#### Scenario: Invalid credential configuration

- **WHEN** an example token or incomplete enabled Salamander configuration reaches a credential boundary
- **THEN** the system does not publish or accept it as usable authority.

### Requirement: REQ-AUDIT-INGRESS — Explicit ingress authority

Protected HTTP routes MUST hide backend method errors. Tailnet SSH MUST require approved private input. Provider checks MUST require explicit default-drop policy, valid firewall attachment authority and appropriate address and port selectors.

#### Scenario: Incomplete ingress configuration

- **WHEN** a request uses an unsupported method or a provider plan lacks required ingress safeguards
- **THEN** nginx returns the uniform not-found response or the plan checker issues a denial, respectively.
