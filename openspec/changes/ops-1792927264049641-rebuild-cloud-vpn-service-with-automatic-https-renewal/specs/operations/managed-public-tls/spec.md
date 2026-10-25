## Purpose

Provide public HTTPS certificates that renew on cloud hosts while the operator workstation is offline.

## ADDED Requirements

### Requirement: REQ-MTLS-AUTHORITY — One active certificate authority

The implementation MUST bind each managed certificate to an explicit domain set and consumer list. It MUST use verified ACME issuance, keep private material out of logs, and prevent an older operator snapshot from replacing a newer active certificate.

#### Scenario: Repeated deployment after renewal

- **WHEN** a managed certificate has renewed and deployment runs with an older encrypted snapshot
- **THEN** the current valid cloud authority is retained, validated and used by every declared consumer.

### Requirement: REQ-MTLS-ACTIVATE — Validated renewal and recovery

The implementation MUST validate the domain set, key match and remaining validity before publication, validate consumer configuration before activation, retain the previous working generation on rejected activation, and expose renewal failure to the observer. Timers MUST run without a personal device.

#### Scenario: Renewal fails

- **WHEN** issuance, validation or consumer activation fails
- **THEN** the previous accepted certificate remains available, the failure is reported without key values, and a later retry does not require the operator workstation.

#### Scenario: Renewal succeeds

- **WHEN** an eligible certificate renews
- **THEN** the declared HTTPS and protocol consumers use the renewed certificate and encrypted backup can recover its private authority.

#### Scenario: Native HTTP-01 solver is idle

- **WHEN** native Hysteria ACME is enabled and no HTTP-01 challenge is active
- **THEN** TCP/80 remains in the exact provider and firewall contract, its absent challenge socket is accepted, and all permanent sockets remain required.
