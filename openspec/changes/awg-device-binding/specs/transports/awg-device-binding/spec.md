## Purpose

Provide observable, testable guarantees for deliver authoritative amneziawg device enrollment and client bindings across accepted inputs, successful operation, failure and retained authority.

## ADDED Requirements

### Requirement: REQ-PROTO-AWG-BIND — Resolve one authoritative device binding

Every enabled AWG profile MUST resolve exactly one host, effective instance and device peer, with listener, server public key and obfuscation parameters identical to the deployed configuration. Missing or ambiguous bindings MUST refuse before returning a successful artifact.

#### Scenario: Two instances with different protocol identity

- **WHEN** two enabled instances use distinct ports, server keys, address pools and headers
- **THEN** each explicitly selected device profile carries only its selected instance values and the other instance remains unchanged

#### Scenario: Missing or ambiguous device binding

- **WHEN** a peer is absent from the selected instance or the selection matches more than one host or instance
- **THEN** issuance returns a categorical error and publishes no successful partial profile

### Requirement: REQ-PROTO-AWG-ENROLL — Enroll and revoke in the effective instance pool

The implementation MUST Enrollment and revocation MUST modify the selected effective instance under the existing shared credential lock, allocate distinct per-device keys and noncolliding host addresses from its pool, and preserve unrelated devices, instances and transport credentials.

#### Scenario: Custom pool enrollment and one-device revocation

- **WHEN** two devices enroll into separate technical pools and one selected device is revoked
- **THEN** the correct server peer collections change, the remaining device still authenticates, and only the revoked identity loses traffic

#### Scenario: Exhaustion, collision and interrupted encrypted publication

- **WHEN** the selected pool is exhausted, an existing address is reused, or publication fails before atomic replacement
- **THEN** the operation refuses without changing encrypted authority or losing an existing device

### Requirement: REQ-PROTO-AWG-PARITY — Validate parameter relationships across all consumers

The implementation MUST Preflight, server rendering, configuration emission and bundle/liveness validation MUST accept the same supported AWG parameter relationships and reject duplicate or conflicting device prefixes, colliding headers, inverted junk bounds and invalid interface names before host mutation. S3 and S4 MUST remain zero.

#### Scenario: Valid technical cohort reaches authenticated data

- **WHEN** a valid cohort with nondefault port and bounds is selected
- **THEN** all consumers agree on its fingerprint and a real exact-version AWG client carries TCP and UDP traffic

#### Scenario: Invalid relationships fail before publication

- **WHEN** headers collide, junk bounds invert, device prefixes conflict or an interface name exceeds the supported grammar
- **THEN** every supported entry point reports the same redacted contract failure and preserves prior output

### Requirement: REQ-PROTO-AWG-PRIVATE — Preserve private authority during export and migration

The replacement binding contract MUST update every caller without compatibility shims, keep private keys and PSKs out of diagnostic callbacks and unapproved public exports, and preserve prior complete authority and unrelated files on failed migration or export.

#### Scenario: Recipient export has bounded private fields

- **WHEN** a selected device profile is emitted through a public recipient format
- **THEN** only the format-authorized peer material is present and no server private key or other device secret appears

#### Scenario: Unsafe output or contract migration failure

- **WHEN** the output path is unsafe or a document cannot be resolved under the replacement contract
- **THEN** the existing artifact and encrypted authority remain intact and the operation cannot claim success
