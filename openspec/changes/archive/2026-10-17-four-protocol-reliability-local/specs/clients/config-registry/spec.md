## Local completion scope (2026-10-16)

The owner authorizes full local implementation and removes staging soak, external recipient, Android emulator and physical-device acceptance from this change. Completion requires actual pinned local engines, isolated Linux systemd/network namespaces/TUN where applicable, authenticated positive and rejection traffic, compensation, privacy and complete source checks. Synthetic credentials are test inputs; mocks, render-only checks and refusal-only results cannot replace runnable behavior. External devices, provider actions, production rollout and promotion are outside acceptance. Earlier observations below retain their original source and limitations; removed external gates are excluded by this scope revision, never recorded as passed.

## MODIFIED Requirements

### Requirement: REQ-DRIFT-CHECK — Payload drift detection

The implementation MUST re-materialize the selected device payload from current repository, SOPS and resolved endpoint inputs and compare a private versioned HMAC over the canonical selected-device payload and exact delivery options with the recorded delivery, reporting stale, current or unknown without retaining the delivered plaintext file.

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
- **THEN** the check reports stale and prints a categorical consumed-payload change without exposing a digest

#### Scenario: Unchanged fleet reports current

- **WHEN** the drift check runs with no relevant source or output change since last delivery
- **THEN** the check reports current and exits zero

#### Scenario: Drift check without registry entry

- **WHEN** the drift check runs for a device with no registry entry
- **THEN** the check reports unknown with a non-zero exit and does not guess defaults
