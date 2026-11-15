## Purpose

Every production AmneziaWG instance has its own junk, padding and port values, none of which this repository publishes, and no header value that is a WireGuard message type.

## ADDED Requirements

### Requirement: REQ-PROTO-AWG-SHAPE-GENERATED — Generate junk and padding values per instance

Instance creation MUST draw `jc`, `jmin`, `jmax`, `s1` and `s2` from a cryptographic random source inside the bounds that the transport semantics define. The result MUST satisfy the existing parameter relationships, including ordered junk bounds and different initiation and response sizes.

#### Scenario: Two new instances

- **WHEN** the operator creates two instances
- **THEN** each has explicit junk and padding values, and the two value sets differ with overwhelming probability

#### Scenario: Degenerate draw

- **WHEN** a draw would make the initiation and response sizes equal
- **THEN** the generator draws again and never writes that value set

### Requirement: REQ-PROTO-AWG-SHAPE-EXPLICIT — Refuse implicit and published values on production

Strict validation for a production document MUST refuse an instance that omits any of `jc`, `jmin`, `jmax`, `s1` or `s2`, and an instance whose five values equal the value set in the committed secrets example. A staging document MUST still validate with either.

#### Scenario: Omitted value on production

- **WHEN** a production instance has no `s2`
- **THEN** validation fails and names the instance and the key

#### Scenario: Example values on production

- **WHEN** a production instance has the five values of the committed example
- **THEN** validation fails

#### Scenario: Staging document

- **WHEN** a staging instance omits the values
- **THEN** validation passes

### Requirement: REQ-PROTO-AWG-SHAPE-HEADERS — Refuse WireGuard message types as header values on production

On a host whose inventory `env` is `prod`, the AmneziaWG role MUST refuse an instance in which any of `h1` to `h4` is a value from 1 to 4, whatever its padding values are, unless a recorded measurement exists for that instance.

#### Scenario: Standard headers with padding

- **WHEN** `env` is `prod`, an instance has `h4` equal to `4` and non-zero `s1` and `s2`, and no measurement is recorded
- **THEN** the role fails before any host mutation

#### Scenario: Recorded measurement

- **WHEN** the same instance has a recorded measurement
- **THEN** the role proceeds

### Requirement: REQ-PROTO-AWG-SHAPE-PORT — Use an instance port that is not the WireGuard default

Instance creation MUST draw the listen port from a random source. Production validation MUST refuse the WireGuard default port. The provider roots MUST open the AmneziaWG port only from the listener contract, and their legacy listener list MUST NOT contain an AmneziaWG entry.

#### Scenario: Default port on production

- **WHEN** a production instance listens on the WireGuard default port
- **THEN** validation fails

#### Scenario: Legacy listener list

- **WHEN** a provider root is planned with the legacy listener list
- **THEN** the plan opens no AmneziaWG port

#### Scenario: Listener contract

- **WHEN** the listener contract names the instance port
- **THEN** the provider firewall opens exactly that UDP port for both address families
