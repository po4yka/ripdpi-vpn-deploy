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

The public manifest MUST distinguish immutable `amneziawg-go` engine identity
from client-produced RIPDPI acceptance. Client acceptance MUST bind exact source,
APK, report and correlation digests, timestamps, AmneziaWG transport, and the
TCP, UDP, recovery, stale-key rejection and cleanup outcomes.

Each executor MUST create a fresh, expiring nonce request bound to its invocation
and MUST accept only a canonical Ed25519-signed handoff over the nonce,
invocation ID and complete acceptance. It MUST consume that handoff once and
MUST reject replay, mutation, unsafe metadata or an invalid signature without
claiming live acceptance.

#### Scenario: Evidence is consumed by both repositories

- **GIVEN** a completed acceptance run
- **WHEN** each repository validates its evidence contract
- **THEN** both repositories MUST apply the structural schema and canonical executable validator, accept the same redacted manifest, and reject a modified or stale copy

The JSON Schema is structural only. Cross-field correlation, time ordering and
recurring-pair relations MUST be decided by the canonical executable validator;
schema acceptance alone MUST NOT be treated as PASS by a deploy or client
consumer.

#### Scenario: Engine provenance cannot substitute for client acceptance

- **GIVEN** a pinned `amneziawg-go` commit and binary digest but no valid client acceptance
- **WHEN** the manifest is validated
- **THEN** it MUST remain non-passing and MUST NOT reinterpret engine fields as RIPDPI client evidence

#### Scenario: Recurring evidence is distinct and ordered

- **GIVEN** one retained passing observation
- **WHEN** a later invocation is considered for publication
- **THEN** it MUST use a later window and distinct invocation, report, and correlation identities or the retained PASS MUST remain unchanged

#### Scenario: Client authentication remains an explicit external boundary

- **GIVEN** deploy-side signature verification but no client signer/relay
- **WHEN** the offline source is evaluated for completion
- **THEN** the live client and recurring acceptance steps MUST remain open
