## Purpose

Keep signature packets unique per instance so that no packet becomes a shared fleet signature.

## ADDED Requirements

### Requirement: REQ-AWG-SIG-GENERATE — Per-instance generation

Instance creation MUST draw each signature packet from a cryptographic random source within the admitted bounds.

#### Scenario: new instance

- **WHEN** an instance is created
- **THEN** its signature packets differ from every other instance in the same secrets file

### Requirement: REQ-AWG-SIG-UNIQUE — No repeated packet

The production guard MUST refuse an instance set in which the static part of a signature packet is byte-identical on two instances or hosts.

#### Scenario: repeat on two nodes

- **WHEN** two instances carry the same static packet part
- **THEN** production refuses the set

### Requirement: REQ-AWG-SIG-NOT-DEFAULT — No public default

The production guard MUST refuse a signature packet whose digest matches the pinned list of public default digests.

#### Scenario: default packet

- **WHEN** an instance carries a packet that matches a pinned digest
- **THEN** production refuses the instance

#### Scenario: staging

- **WHEN** the same packet runs in a staging lane
- **THEN** the measurement exception applies, like the header guard
