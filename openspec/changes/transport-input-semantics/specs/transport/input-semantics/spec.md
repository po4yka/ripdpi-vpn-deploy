## Purpose

Provide observable, testable guarantees for reject incoherent transport inputs before runtime mutation across accepted inputs, successful operation, failure and retained authority.

## ADDED Requirements

### Requirement: REQ-PROTO-INPUT-COHORT — Complete cohort membership

The implementation MUST require explicit, nonempty and valid client references for each enabled REALITY cohort before rendering or publishing any runtime.

#### Scenario: Accepted cohort renders

- **WHEN** a complete cohort names unique existing clients
- **THEN** the actual renderer and pinned Xray parser accept it

#### Scenario: Missing or invalid references refuse

- **WHEN** clients is absent, empty, duplicated or contains an unknown device
- **THEN** preflight fails before any install, restart or configuration write

### Requirement: REQ-PROTO-INPUT-AWG — Shared AWG relationships

The implementation MUST apply the same effective-instance parameter, interface-name and peer-address relationship checks in schema/preflight, enrollment, server rendering, bundle and liveness consumers.

#### Scenario: Valid custom and multi-instance inputs

- **WHEN** distinct headers and ordered junk bounds describe unique valid peer addresses
- **THEN** all consumers accept the same effective values

#### Scenario: Invalid relationships refuse early

- **WHEN** junk bounds invert, headers collide, names violate grammar or issued address claims collide
- **THEN** validation names the categorical field and no host or credential mutation occurs

### Requirement: REQ-PROTO-INPUT-HYSTERIA — Masquerade agreement

The implementation MUST accept only the supported owned HTTPS proxy masquerade contract across schema, role preflight and installed validation.

#### Scenario: Owned proxy passes

- **WHEN** proxy masquerade points at the validated served canonical origin
- **THEN** the rendered candidate passes actual configured validation

#### Scenario: Unsupported mode refuses consistently

- **WHEN** a document requests 404, file, string or an unowned origin
- **THEN** schema/preflight rejects it before publication rather than failing after installation

### Requirement: REQ-PROTO-INPUT-PRIVACY — Private validation diagnostics

The implementation MUST validate field relationships without disclosing passwords, private keys, peer material or bearer identifiers in errors and preserve the arm64 floor.

#### Scenario: Synthetic sensitive values fail

- **WHEN** a malformed document contains distinctive credential markers
- **THEN** stdout/stderr contain only categorical field diagnostics and no marker

#### Scenario: Floor remains enforced

- **WHEN** any source proposes nonzero S3 or S4 without a verified floor
- **THEN** all affected consumers refuse and the floor policy is unchanged
