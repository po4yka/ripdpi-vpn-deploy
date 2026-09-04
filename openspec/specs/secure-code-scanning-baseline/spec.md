# secure-code-scanning-baseline Specification

## Purpose
Keep repository-owned Python and local Xray observability code free of the
identified CodeQL defects while preserving least-privilege metric collection,
bounded probe behavior, and redacted failure diagnostics.
## Requirements
### Requirement: REQ-SECURE-TEXTFILE-ACCESS — Restrict Xray metrics to required readers

The implementation MUST atomically publish the Xray diagnostic textfile with
owner read/write and shared-group read access only, MUST grant the
node_exporter service account membership in that shared group, and MUST retain
the Xray exporter as the file owner.

#### Scenario: Fresh monitoring convergence

- **WHEN** the monitoring role converges on a node with Xray diagnostics enabled
- **THEN** `vpn_xray.prom` is owned by the Xray runtime account and shared textfile group, has mode `0640`, and is readable through node_exporter

#### Scenario: Existing permissive metric is repaired

- **WHEN** an existing `vpn_xray.prom` is world-readable
- **THEN** the next monitoring convergence removes world access without leaving stale ownership or preventing a subsequent atomic exporter update

#### Scenario: Xray diagnostics are disabled

- **WHEN** no enabled transport requires Xray diagnostics
- **THEN** the role continues to stop and remove the exporter units, binary, and metric rather than preserving an inaccessible stale file

### Requirement: REQ-REDACTED-FALLBACK-FAILURE — Report failed failure-metric writes

The implementation MUST return a failure when Xray collection fails, SHOULD
publish the redacted collection-failure metric, and MUST emit a redacted
diagnostic when that fallback metric cannot be written instead of silently
discarding the write error.

#### Scenario: Collection and fallback write both fail

- **WHEN** the StatsService query fails and the failure-metric write raises an operating-system error
- **THEN** the exporter writes only safe error categories to stderr, returns non-zero, and does not reveal metric contents, paths, credentials, or raw Xray output

#### Scenario: Collection fails but fallback write succeeds

- **WHEN** the StatsService query fails and the output path remains writable
- **THEN** stale counters are atomically replaced with `vpn_xray_stats_collection_success 0` and the exporter returns non-zero

### Requirement: REQ-BOUNDED-PORT-READINESS — Preserve explicit bounded readiness retries

The protocol-liveness sentinel MUST treat connection refusal during its
bounded local-port readiness window as a retryable not-ready observation, and
MUST still fail readiness when the child exits or the deadline expires.

#### Scenario: Listener becomes ready within the deadline

- **WHEN** a local probe connection initially raises an operating-system error and later succeeds before the deadline
- **THEN** readiness succeeds without leaking an exception or extending the configured deadline

#### Scenario: Listener never becomes ready

- **WHEN** every local probe connection fails until the deadline or the child process exits
- **THEN** readiness fails and the existing fail-closed probe result is preserved

### Requirement: REQ-CODEQL-ALERT-CLOSURE — Clear the identified alert set in source

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
