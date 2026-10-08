## Purpose

Complete a real first subscription-host dry-run while preserving existing service checks and refusing ambiguous unit discovery.

## ADDED Requirements

### Requirement: REQ-SUB-PLANNED-UNIT — Planned absent unit

Check mode MUST defer absent vpn-bootstrap.service activation only when its template plans installation.

#### Scenario: First dry-run

- **WHEN** LoadState is not-found and the template plans a change
- **THEN** activation is deferred without creating or starting the service.

#### Scenario: Unplanned absence

- **WHEN** the unit is absent without a planned template change
- **THEN** the role refuses before activation.

### Requirement: REQ-SUB-ACTIVATION — Existing and real units

The role MUST retain loaded service checks and real deployment activation.

#### Scenario: Loaded check mode

- **WHEN** LoadState is loaded during check mode
- **THEN** the normal systemd module checks activation.

#### Scenario: Real deployment

- **WHEN** deployment installs the unit outside check mode
- **THEN** systemd reloads, enables and starts it.

### Requirement: REQ-SUB-DISCOVERY — Fail closed discovery

Check mode MUST refuse unknown or failed systemd discovery.

#### Scenario: Invalid discovery

- **WHEN** systemd discovery fails or returns an unsupported state
- **THEN** the role refuses instead of treating the unit as absent.
