## Purpose

Provide observable, testable guarantees for detect client payload drift from every consumed private input across accepted inputs, successful operation, failure and retained authority.

## ADDED Requirements

### Requirement: REQ-PROTO-IDENTITY-ISSUANCE — Delivery identity matches exact artifact

The implementation MUST compute and record the identity from the exact selected-device bytes/options delivered by issue-sub-token, within its existing atomic transaction.

#### Scenario: Multi-host binding is delivered

- **WHEN** RIPDPI format, two hosts and an explicit AWG instance are selected
- **THEN** artifact and recorded identity describe those exact choices

#### Scenario: Recording fails

- **WHEN** private registry write fails after candidate materialization
- **THEN** no success is reported and prior encrypted authority remains intact

### Requirement: REQ-PROTO-IDENTITY-PRIVACY — Safe failure and diagnostics

The implementation MUST keep plaintext material and digest authority out of logs, argv, persisted temporary caches and public identity metadata.

#### Scenario: Reader or renderer fails

- **WHEN** SOPS permission, parse, endpoint lookup or renderer failure occurs
- **THEN** unknown/nonzero is returned within a deadline without exposing material

#### Scenario: Sensitive marker propagates

- **WHEN** distinctive synthetic credentials enter the materializer
- **THEN** all diagnostic and public artifact surfaces omit them except the authorized selected-device private payload

### Requirement: REQ-PROTO-IDENTITY-AUTHORITY — Versioned private identity authority

The implementation MUST use a versioned domain-separated keyed identity with encrypted private authority and recorded generation; missing, malformed, unavailable or changed authority MUST produce unknown without replacement generation during inspection.

#### Scenario: Comparable authority succeeds

- **WHEN** delivery and inspection use the same validated authority generation and canonical selected-device inputs
- **THEN** identity comparison produces the correct current or stale verdict without exposing authority or digest

#### Scenario: Lost or changed authority is unknown

- **WHEN** authority is lost rotated malformed unavailable or differs from the recorded generation
- **THEN** inspection returns unknown without creating replacement material comparing incomparable identities or mutating SOPS
