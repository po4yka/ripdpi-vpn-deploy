## Purpose

Provide observable, testable guarantees for detect client payload drift from every consumed private input across accepted inputs, successful operation, failure and retained authority.

## MODIFIED Requirements

### Requirement: REQ-DRIFT-CHECK — Payload drift detection

The implementation MUST re-materialize the selected device payload from current repository, SOPS and resolved endpoint inputs and compare a private versioned identity with the recorded delivery, reporting stale, current or unknown without retaining the delivered plaintext file.

#### Scenario: Private consumed value changes

- **WHEN** a device password, peer key, SNI, bound instance, supported parameter or token expiry changes after delivery
- **THEN** the identity changes and client-drift reports stale without printing the value

#### Scenario: Unconsumed inputs change

- **WHEN** only SOPS ciphertext wrapping or another device credential changes
- **THEN** the selected device remains current

#### Scenario: No usable recorded identity

- **WHEN** the record is absent or lacks the new validated identity generation
- **THEN** the verdict is unknown and no delivery or credential mutation occurs

#### Scenario: Endpoint change detected as drift

- **WHEN** a node IP changes after payload delivery and the operator runs make client-drift CLIENT=<device>
- **THEN** the check reports stale and prints the identity delta

#### Scenario: Unchanged fleet reports current

- **WHEN** the drift check runs with no relevant source or output change since last delivery
- **THEN** the check reports current and exits zero

#### Scenario: Drift check without registry entry

- **WHEN** the drift check runs for a device with no registry entry
- **THEN** the check reports unknown with a non-zero exit and does not guess defaults
