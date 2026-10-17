## Purpose

Provide observable, testable guarantees for deliver topology-aware authenticated transport health and secure smoke probes across accepted inputs, successful operation, failure and retained authority.

## ADDED Requirements

### Requirement: REQ-PROTO-PROBE-TOPOLOGY — Inspect every effective transport surface

The implementation MUST Ordinary verification and watchdog MUST derive complete target sets from effective REALITY cohorts, XHTTP frontend/backend ownership, Hysteria settings and all AWG instance bindings. Valid nondefault layouts MUST pass and failure of any required target MUST be visible without testing an absent legacy base port or interface.

#### Scenario: Cohort-only and multiple-instance topology

- **WHEN** REALITY excludes the base port and AWG has two custom instance names
- **THEN** all actual targets are checked, nonexistent legacy targets are omitted and healthy topology causes no recovery

#### Scenario: One secondary instance or shared backend fails

- **WHEN** one AWG instance or the XHTTP backend is unavailable while other listeners are healthy
- **THEN** the combined result fails for the affected capability and identifies only its owned recovery target

### Requirement: REQ-PROTO-PROBE-AUTH — Prove authenticated traffic with production-equivalent client settings

A transport success MUST require authenticated data delivery through its selected canonical client. Hysteria smoke MUST use effective SNI, trusted TLS validation and matching Salamander; local listener presence and an insecure handshake MUST never count as equivalent proof.

#### Scenario: Secure obfuscated and distinct-name Hysteria

- **WHEN** Hysteria uses its own certificate hostname and Salamander is enabled
- **THEN** the matching secure smoke client delivers the controlled request through the owned proxy

#### Scenario: Wrong credential, SAN or trust anchor

- **WHEN** the selected password is wrong or certificate name or trust validation fails
- **THEN** the authenticated result is unhealthy even if the port is open and the direct control target succeeds

### Requirement: REQ-PROTO-PROBE-OWNERSHIP — Bound probe lifecycle and recovery ownership

The implementation MUST Probe starts, waits, requests and cleanup MUST have bounded deadlines and invocation-bound ownership. Recovery MUST preserve existing durable budgets and affect only the exact failing owned runtime; credentials MUST remain outside ordinary callback, process and evidence output.

#### Scenario: Foreign listener and occupied private workdir

- **WHEN** a different process owns the probe port or another invocation owns the work directory
- **THEN** the new run refuses without adopting success or stopping or deleting another owner resource

#### Scenario: Probe or notification stalls and cleanup is uncertain

- **WHEN** a client, control request or notification exceeds its bound or its cleanup cannot be confirmed
- **THEN** supervision remains bounded, the prior recovery budget remains complete, and uncertain owned state blocks unsafe reuse

### Requirement: REQ-PROTO-PROBE-EVIDENCE — Separate positive runtime proof from source and deployment claims

The implementation MUST Results MUST identify exact source, runtime, topology and observed boundary, distinguish direct controls from transport delivery, and replace stale healthy status with redacted failure. Native warm AWG adoption and Hysteria hopping MUST observe actual processes and traffic rather than script versions or render assertions.

#### Scenario: Pin-only or unit-only AWG warm update

- **WHEN** an active exact AWG daemon receives a binary pin-only or unit-only update with unchanged private config
- **THEN** the running process and sandbox adopt the selected runtime and a third unchanged convergence causes no restart

#### Scenario: Hopping and malformed evidence

- **WHEN** real Hysteria traffic traverses several owned range ports or a required result becomes malformed
- **THEN** hopped traffic and unrelated outbound UDP are measured separately, and malformed evidence cannot preserve a fresh healthy result
