## Local completion scope (2026-10-16)

The owner authorizes full local implementation and removes staging soak, external recipient, Android emulator and physical-device acceptance from this change. Completion requires actual pinned local engines, isolated Linux systemd/network namespaces/TUN where applicable, authenticated positive and rejection traffic, compensation, privacy and complete source checks. Synthetic credentials are test inputs; mocks, render-only checks and refusal-only results cannot replace runnable behavior. External devices, provider actions, production rollout and promotion are outside acceptance. Earlier observations below retain their original source and limitations; removed external gates are excluded by this scope revision, never recorded as passed.

## Purpose

Provide observable, testable guarantees for deliver coordinated hysteria ech server and recipient profiles across accepted inputs, successful operation, failure and retained authority.

## ADDED Requirements

### Requirement: REQ-PROTO-ECH-CONTRACT — Bind coordinated server and recipient ECH capabilities

An ECH-enabled profile MUST bind exact supported server and recipient runtime capabilities, typed public configuration and explicit inner/outer TLS identity. Every selected emitter, parser and liveness client MUST consume the same generation. Unsupported engines MUST refuse before producing a usable ECH profile, and at least one supported engine MUST deliver the positive capability.

#### Scenario: Supported recipient imports a coordinated profile

- **WHEN** the selected server and supported recipient engine receive the same validated ECH generation
- **THEN** the actual parser imports it and a real authenticated connection succeeds with the intended inner and outer identity

#### Scenario: Unsupported engine or invalid public configuration

- **WHEN** an engine lacks the required ECH capability or public configuration is malformed
- **THEN** export or import refuses categorically without silently stripping ECH or claiming feature completion

### Requirement: REQ-PROTO-ECH-PRIVATE — Keep ECH authority private and TLS verification intact

The implementation MUST Private ECH keys MUST stay in encrypted server authority and root-owned runtime delivery; public artifacts and diagnostics MUST contain only authorized public configuration. TLS trust and inner-name verification MUST remain enabled, and ECH-required profiles MUST not silently fall back to unencrypted ClientHello or insecure certificate acceptance.

#### Scenario: Verified encrypted ClientHello connection

- **WHEN** the supported recipient connects with valid public ECH configuration and certificate authority
- **THEN** authenticated traffic succeeds, observed ClientHello behavior matches the required encrypted profile, and no private key enters output

#### Scenario: Wrong certificate or ECH negotiation failure

- **WHEN** certificate trust or name is wrong or required ECH negotiation fails
- **THEN** the connection fails and direct plaintext or insecure fallback cannot satisfy acceptance

### Requirement: REQ-PROTO-ECH-ACTIVATE — Publish and compensate complete ECH authority generations

The implementation MUST ECH authority, configuration and runtime activation MUST form a complete validated generation with durable activation intent. Failed validation, interrupted activation or readiness failure MUST retain or restore the prior complete ready authority; unsafe or unknown state MUST refuse without deletion. Rotation MUST preserve explicitly documented recipient generation semantics.

#### Scenario: Rotation followed by unchanged convergence

- **WHEN** a valid ECH generation rotates and is then converged unchanged
- **THEN** the running process adopts it, supported recipients connect under the declared generation contract, and repeated convergence is idempotent

#### Scenario: Interrupted or failed authority activation

- **WHEN** publication is interrupted or candidate readiness fails
- **THEN** the next safe retry reconciles known intent or restores the prior complete authority while unrelated private files and services remain untouched

### Requirement: REQ-PROTO-ECH-ACCEPT — Require measured supported-client acceptance and eligible promotion

The implementation MUST ECH feature acceptance MUST include actual supported recipient parser and connection behavior, authenticated TCP UDP DNS traffic, explicit certificate/negotiation failures and packet identity observations. Local acceptance MUST bind exact supported server/parser artifacts to their reviewed digests and actual isolated traffic. Production promotion remains separately authorized; missing current release/advisory eligibility keeps promotion ineligible and cannot be reported as passed.

#### Scenario: Local protocol engines and paired profiles

- **WHEN** exact eligible server and recipient versions complete the bounded isolated local ECH matrix
- **THEN** positive traffic reconnect and required privacy behavior are observed with source/runtime identities and no unverified engine is marked supported

#### Scenario: Parser-only or incomplete local protocol behavior

- **WHEN** only a parser passes, actual local protocol engines cannot be exercised or their identity is unverified
- **THEN** the feature stays unfinished and records the missing boundary without treating refusal, mocks or old receipt data as success
