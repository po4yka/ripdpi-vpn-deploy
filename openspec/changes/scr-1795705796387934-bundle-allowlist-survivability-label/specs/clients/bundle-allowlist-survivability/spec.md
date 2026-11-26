## Purpose

Tell the client which transport entries can pass under an allowlist regime, without claiming that any address is permitted.

## ADDED Requirements

### Requirement: REQ-ALLOW-LABEL — Optional per-entry label

The bundle MUST allow one label per transport entry with the values yes, no and unknown. The validator MUST reject any other value. An absent label MUST mean unknown.

#### Scenario: valid label

- **WHEN** an entry carries the value no
- **THEN** the validator accepts the bundle

#### Scenario: invalid label

- **WHEN** an entry carries another value
- **THEN** the validator rejects the bundle

### Requirement: REQ-ALLOW-TABLE — Label comes from the class table

The emitter MUST derive the label from a repository-owned table keyed by transport class. It MUST NOT emit yes for a class that has no table entry.

#### Scenario: UDP class

- **WHEN** an entry uses a UDP-based class
- **THEN** the emitter writes no

#### Scenario: unlisted class

- **WHEN** an entry uses a class with no table entry
- **THEN** the emitter writes unknown

### Requirement: REQ-ALLOW-ADVISORY — Label is advisory

The server MUST NOT infer the regime. The label MUST NOT assert that an address is permitted.

#### Scenario: label yes

- **WHEN** an entry has the value yes
- **THEN** the documentation states that the address can still be blocked
