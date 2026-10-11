## Purpose

Provide observable, testable guarantees for upgrade verified recipient parsers to the current stable client line across accepted inputs, successful operation, failure and retained authority.

## ADDED Requirements

### Requirement: REQ-PROTO-PARSER-INTEGRITY — Verified stable artifacts

The implementation MUST select a stable non-prerelease client parser with exact reviewed architecture digests and verify its bytes before executing any command.

#### Scenario: Verified supported artifact

- **WHEN** the candidate stable tag and digest match a supported architecture
- **THEN** version identity is exact and parser commands execute

#### Scenario: Artifact identity fails

- **WHEN** archive is truncated, tampered, wrong architecture or has unknown release status
- **THEN** installation/execution refuses without replacing the prior complete tool

### Requirement: REQ-PROTO-PARSER-PAYLOADS — Supported full payload compatibility

The implementation MUST parse complete canonical recipient artifacts with the exact appropriate engines and pass the named native traffic contract.

#### Scenario: Supported delivery formats

- **WHEN** all baseline and selected supported modes are emitted for single/multi-host bindings
- **THEN** full configurations parse and exact clients complete the integration cases

#### Scenario: Unsupported transport or removed field

- **WHEN** a selected parser cannot represent XHTTP/AWG or a candidate removes a consumed field
- **THEN** the explicit compatible emitter/engine route is used or preflight refuses with a migration requirement, never silent field omission

### Requirement: REQ-PROTO-PARSER-ROLLBACK — Atomic adoption and clear evidence

The implementation MUST preserve a verified prior parser and complete inputs until candidate compatibility passes, recording client and server identities independently.

#### Scenario: Compatibility fails

- **WHEN** native or full-parser acceptance of the candidate fails
- **THEN** prior parser contract remains usable and upgrade is not promoted

#### Scenario: Candidate passes

- **WHEN** all required exact-engine gates pass
- **THEN** only reviewed pin/hash/config changes are published and no fleet deployment is implied

### Requirement: REQ-PROTO-PARSER-ELIGIBILITY — Release eligibility is distinct from source adoption

The implementation MUST refresh candidate channel publication hash and advisory metadata at execution and require at least 48 hours of stable publication eligibility before production recipient redistribution or promotion, without treating source adoption as deployment authorization.

#### Scenario: Young verified parser remains source-testable

- **WHEN** verified stable candidate bytes are compatible but publication age is below 48 hours
- **THEN** source/parser tests may pass while promotion is explicitly ineligible and no recipient redistribution occurs

#### Scenario: Unknown eligibility blocks promotion

- **WHEN** channel publication hash or relevant advisory status cannot be verified
- **THEN** promotion refuses with the missing eligibility named and prior supported delivery remains intact
