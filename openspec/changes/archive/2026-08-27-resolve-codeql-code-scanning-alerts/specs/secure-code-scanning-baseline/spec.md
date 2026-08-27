## Purpose

Keep repository-owned Python and local Xray observability code free of the
identified CodeQL defects while preserving least-privilege metric collection,
bounded probe behavior, and redacted failure diagnostics.

## ADDED Requirements

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

The implementation MUST remove the causes of CodeQL alerts 320 through 327
without dismissals, suppressions, query-pack removal, workflow permission
expansion, or unrelated behavior changes.

#### Scenario: Exact implementation SHA is analyzed

- **WHEN** the hosted Python CodeQL job analyzes the final implementation SHA with `security-extended,security-and-quality`
- **THEN** alerts 320 through 327 are absent and no replacement alert is introduced by the remediation

#### Scenario: Local compatibility checks run

- **WHEN** focused tests exercise task closure, protocol liveness, operator monitoring, Vultr preflight, and Xray observability
- **THEN** existing successful and fail-closed behavior remains compatible apart from the intentional least-privilege file-mode change
