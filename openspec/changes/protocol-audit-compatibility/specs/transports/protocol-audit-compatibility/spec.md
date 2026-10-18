## Purpose

Keep delivered protocol configurations compatible with their pinned engines and
reject invalid identities before runtime mutation or client publication.

## ADDED Requirements

### Requirement: REQ-PROTOCOL-MUX — Compatible P0 client delivery

The exporter MUST refuse sing-mux output for an Xray P0 mux listener. Supported
P0 profiles MUST retain real-engine authentication and data transfer coverage.

#### Scenario: Incompatible mux output

- **WHEN** a sing-box recipient selects a P0 mux listener
- **THEN** generation fails before a client artifact is published

#### Scenario: Supported P0 transport

- **WHEN** real pinned engines consume the supported generated P0 profile
- **THEN** authenticated loopback traffic succeeds and invalid credentials fail

### Requirement: REQ-PROTOCOL-MTG — Valid mtg installation and input

The research role MUST extract the checksum-pinned official archive and validate
FakeTLS secret structure before runtime mutation. Invalid inputs MUST not be logged.

#### Scenario: Official release archive

- **WHEN** an admitted architecture uses the pinned official mtg archive
- **THEN** the published executable passes native version and configuration checks

#### Scenario: Existing same-version receipt

- **WHEN** the old role has published an immutable raw-binary receipt at the upstream version
- **THEN** the corrected archive uses a distinct local release identity and preserves the old receipt

#### Scenario: Invalid FakeTLS input

- **WHEN** a secret lacks the FakeTLS prefix, key, or valid hostname
- **THEN** admission refuses before installation or service activation

### Requirement: REQ-PROTOCOL-IDENTITY — Unique REALITY wire identities

Admission MUST require even-length valid hex shortIds and reject duplicate
eight-byte wire values across devices, including case and zero-padding aliases.

#### Scenario: Alias or malformed shortId

- **WHEN** input contains odd hex or equivalent wire values for two devices
- **THEN** semantic admission rejects it without printing the values

### Requirement: REQ-PROTOCOL-NAIVE — Private CONNECT error handling

Naive MUST exclude request-bearing HTTP error logs. The exact role-owned runtime
MUST be tested with CONNECT failure paths and valid authenticated traffic.

#### Scenario: Failed CONNECT

- **WHEN** a synthetic CONNECT request fails or resets
- **THEN** retained logs contain no client request or destination metadata

### Requirement: REQ-PROTOCOL-PQE — Preserve the PQE HOLD

REALITY VLESS decryption MUST remain none with no new PQE override. Documentation
MUST distinguish stable engine support from the missing client-delivery contract.

#### Scenario: Classical recipient contract

- **WHEN** server and client configurations are generated
- **THEN** PQE remains unavailable and existing HOLD guards pass

### Requirement: REQ-PROTOCOL-NATIVE — Real optional transport checks

Required CI MUST use real pinned Snell runtimes for the three declared variants,
cover authentication refusal and connection reuse, and test enabled Finalmask
with its typed native schema. Synthetic service fixtures MUST not claim wire proof.

#### Scenario: Pinned optional transport

- **WHEN** the native compatibility lane runs with synthetic local credentials
- **THEN** real parser and data-path checks pass without inventory or provider access

### Requirement: REQ-PROTOCOL-INVENTORY — Single-line inventory metadata

The renderer MUST remove CR and LF from encoded public-listener and
observability-topology metadata. Strict inventory admission MUST remain unchanged.

#### Scenario: CRLF encoder output

- **WHEN** the Base64 encoder emits wrapped CRLF output
- **THEN** each inventory metadata value remains on one line and decodes unchanged
