## Purpose

Define complete, redacted acceptance evidence for the current supported
AmneziaWG client and disposable deployment path.

## ADDED Requirements

### Requirement: REQ-TST-1786299293097217-001 — Acceptance proves real data flow

The acceptance lane MUST prove authenticated bidirectional TCP and UDP traffic
between the current RIPDPI-compatible client and a disposable deployed server.

#### Scenario: Current revision completes the data plane

- **GIVEN** exact client and deploy revisions with valid operator-owned inputs
- **WHEN** the isolated acceptance lane runs
- **THEN** both traffic classes MUST complete and be represented by fresh, redacted evidence

### Requirement: REQ-TST-1786299293097217-002 — Acceptance proves recovery

The lane MUST verify restart, configuration reload, reconnect, recovery, and
teardown without treating a listening process as proof of success.

#### Scenario: Runtime lifecycle remains usable

- **GIVEN** a passing initial data-plane session
- **WHEN** the managed lifecycle sequence is exercised
- **THEN** traffic MUST recover and all temporary resources MUST be removed

### Requirement: REQ-TST-1786299293097217-003 — Negative and unavailable states fail closed

The lane MUST reject stale or partial evidence and MUST report unavailable
infrastructure, missing credentials, and invalid keys as non-passing outcomes.

#### Scenario: Required external input is missing

- **GIVEN** an absent provider input, runner, or credential
- **WHEN** the recurring lane starts
- **THEN** it MUST emit an explicit blocked result and MUST NOT report success

### Requirement: REQ-TST-1786299293097217-004 — Evidence is cross-repository and privacy safe

Evidence MUST bind exact client and deploy revisions, preserve freshness and
completeness, and omit endpoints, credentials, packet contents, and inventory.

#### Scenario: Evidence is consumed by both repositories

- **GIVEN** a completed acceptance run
- **WHEN** each repository validates its evidence contract
- **THEN** both validators MUST accept the same redacted manifest and reject a modified or stale copy
