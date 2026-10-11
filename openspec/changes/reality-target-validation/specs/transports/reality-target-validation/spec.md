## Purpose

Provide observable, testable guarantees for make reality target validation bounded standards-correct and truthful across accepted inputs, successful operation, failure and retained authority.

## ADDED Requirements

### Requirement: REQ-PROTO-RTV-IDENTITY — Standards-correct target identity checking

The implementation MUST Target validation MUST normalize the configured name list once and verify each actual handshake certificate against that exact name using standards-correct hostname matching. A single-label wildcard MUST NOT authorize multiple deeper labels.

#### Scenario: Valid exact and single-label wildcard names pass

- **WHEN** a controlled TLS target presents a trusted valid certificate covering each normalized configured name
- **THEN** each identity check passes and duplicate or separator handling is deterministic

#### Scenario: Deep wildcard or malformed name refuses

- **WHEN** a configured name exceeds wildcard scope or the name list is empty or malformed
- **THEN** identity validation fails categorically and cannot select or mutate a replacement target

### Requirement: REQ-PROTO-RTV-DEADLINES — Finite operation and aggregate budgets

The implementation MUST DNS TLS HTTP metadata lookups and their child process groups MUST terminate within explicit per-operation and whole-run budgets. Timeout MUST remain a failed or unavailable observation and MUST NOT be reported as healthy.

#### Scenario: Bounded healthy run completes

- **WHEN** all controlled target stages respond within their allocated budgets
- **THEN** the full normalized check set completes and reports its actual observations

#### Scenario: TLS or resolver stalls

- **WHEN** a controlled stage stalls or leaves a child running
- **THEN** its owned process group is reclaimed within the run budget and the result is categorical failure without stale healthy state

### Requirement: REQ-PROTO-RTV-CLAIMS — Report only measured client and path capability

The implementation MUST HTTP User-Agent probes MUST be labeled ordinary HTTP/TLS hygiene. Browser ClientHello compatibility MUST require a real exact pinned supported client handshake. Missing client capability or absent filtered vantage MUST remain explicit unavailable evidence and MUST NOT count toward promotion.

#### Scenario: Real supported client handshake succeeds

- **WHEN** a pinned compatible client completes the intended target handshake
- **THEN** the report identifies actual client compatibility separately from hygiene

#### Scenario: Only ordinary curl is available

- **WHEN** ordinary curl succeeds but no actual compatible client or filtered vantage is exercised
- **THEN** HTTP hygiene may pass while client compatibility and filtered survival remain unverified

### Requirement: REQ-PROTO-RTV-OWNERSHIP — Separate owned public service validation from loopback plumbing

The implementation MUST Owned self-steal validation MUST bind the approved public service endpoint and SNI while keeping node-local target plumbing distinct. Validation failure MUST preserve accepted target and certificate authority, never mutate credentials or deployment state, and emit no private values.

#### Scenario: Owned public service path validates

- **WHEN** a controlled self-steal service is reached through its public endpoint with the owned SNI
- **THEN** the observation describes that service path and does not substitute the sentinel's local target socket

#### Scenario: Failed candidate preserves accepted authority

- **WHEN** candidate identity compatibility or deadline checks fail
- **THEN** the accepted target and TLS authority remain untouched and redacted reports name only categorical failure
