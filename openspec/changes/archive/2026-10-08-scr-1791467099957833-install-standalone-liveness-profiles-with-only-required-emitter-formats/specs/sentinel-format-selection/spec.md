## Purpose

Select canonical client emitter formats from actual sentinel profiles while preserving strict input validation and native installation evidence.

## ADDED Requirements

### Requirement: REQ-LIVENESS-REQUIRED-FORMATS — Emit only required inputs

The installer MUST request sing-box for REALITY or Hysteria2 and RIPDPI for XHTTP, and MUST NOT request an unused format. AWG-only MUST use the existing canonical AWG resolver without either JSON emitter.

#### Scenario: Standalone XHTTP

- **WHEN** a sentinel requires only P1 XHTTP
- **THEN** only the RIPDPI emitter runs and the real Xray parser validates the prepared profile.

#### Scenario: Standalone native transports

- **WHEN** a sentinel requires only REALITY or Hysteria2
- **THEN** only the sing-box emitter runs.

#### Scenario: AWG-only and mixed profiles

- **WHEN** a sentinel requires AWG only or a mixed profile set
- **THEN** no JSON emitter runs for AWG-only, and each required format runs once for mixed profiles.

### Requirement: REQ-LIVENESS-EMITTER-REFUSAL — Preserve strict preparation

A required emitter failure MUST refuse before remote writes; unused formats MUST NOT be filled with synthetic successful profiles. Target identity, TLS validation, native parsers, pending state and committed generation receipt checks MUST remain enforced.

#### Scenario: Required emitter fails

- **WHEN** a required canonical emitter fails
- **THEN** onboarding refuses without publishing an assignment or transferring remote material.
