## Purpose

Keep repository-owned Python free of identified CodeQL defects while preserving
fail-closed promotion, probe validation, redacted diagnostics, and bounded cleanup.

## ADDED Requirements

### Requirement: REQ-EXPLICIT-DESCRIPTOR-CLEANUP — Make cleanup failure semantics explicit

Best-effort cleanup of locally owned file descriptors MUST be explicit, MUST
remain bounded, and MUST NOT expose paths, state content, or raw exception text.
The outer operation MUST retain its established typed failure result.

#### Scenario: Descriptor was never opened

- **WHEN** a protected snapshot open or validation operation fails before a file descriptor is assigned
- **THEN** cleanup completes without replacing the canonical `terraform-snapshot-invalid` result with an unbound-local error

#### Scenario: Descriptor close also fails

- **WHEN** validation has already selected the canonical invalid-snapshot result and closing its local descriptor raises an operating-system error
- **THEN** the operation still returns only the canonical result and emits no sensitive diagnostic

## MODIFIED Requirements

### Requirement: REQ-CODEQL-ALERT-CLOSURE — Clear the identified alert sets in source

The implementation MUST preserve closure of CodeQL alerts 320 through 327 and
MUST remove the causes of CodeQL alerts 424 and 511 through 513 without
dismissals, suppressions, query-pack removal, workflow permission expansion, or
unrelated behavior changes.

#### Scenario: Exact implementation SHA is analyzed

- **WHEN** the hosted Python CodeQL job analyzes the final implementation SHA with `security-extended,security-and-quality`
- **THEN** alerts 320 through 327, 424, and 511 through 513 are absent and no replacement alert is introduced by the remediation

#### Scenario: Local compatibility checks run

- **WHEN** focused tests exercise protocol liveness, safe descriptor cleanup, trusted Terraform validation, and Tailnet network promotion
- **THEN** existing successful and fail-closed behavior remains compatible while every intentionally ignored cleanup failure is explicit
