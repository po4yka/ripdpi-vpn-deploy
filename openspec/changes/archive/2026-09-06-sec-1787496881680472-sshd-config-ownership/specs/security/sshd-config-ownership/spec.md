## Purpose

SSH server configuration on managed nodes has a single deterministic owner per directive, converges fail-closed on cross-file conflicts, is validated as assembled rather than fragment-wise, and negotiates only pinned algorithms regardless of provider image defaults.

## ADDED Requirements

### Requirement: REQ-SSHD-SINGLE-OWNER — Every sshd directive MUST have exactly one owning file per host

The boot-critical drop-in and the Ansible-managed drop-in MUST NOT repeat any directive key; convergence MUST fail when duplication is detected.

#### Scenario: future hardening edit

- **WHEN** an operator changes a tunable directive in the managed drop-in
- **THEN** the effective configuration reflects the edit after reload

#### Scenario: drift reintroducing overlap

- **WHEN** a directive appears in both drop-ins
- **THEN** convergence fails naming the duplicated keys before any service change

### Requirement: REQ-SSHD-EFFECTIVE-VALIDATION — Validation MUST cover the effective assembled configuration

sshd validation during converge MUST evaluate the effective parsed configuration rather than a single fragment in isolation.

#### Scenario: conflicting out-of-band drop-in

- **WHEN** an unmanaged file shadows a managed directive
- **THEN** the effective-config validation step detects the mismatch and fails convergence

### Requirement: REQ-SSHD-ALGO-PIN — SSH algorithm negotiation MUST be pinned at the managed layer

Ciphers, MACs, and key-exchange algorithms MUST be explicitly configured by the managed drop-in and asserted post-converge.

#### Scenario: heterogeneous provider images

- **WHEN** nodes from different providers converge
- **THEN** effective algorithm sets match the pinned allowlist on every host
