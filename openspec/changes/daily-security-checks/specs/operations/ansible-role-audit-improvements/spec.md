## Purpose

Extend explicit host audits with private service-isolation evidence while
preserving the existing reporting and acceptance boundaries.

## ADDED Requirements

### Requirement: REQ-AUDIT-SYSTEMD — Retain systemd isolation diagnostics

The existing explicit audit MUST run `systemd-analyze security` without a pager
and retain its return code, stdout and error diagnostics in a mode-0640 report.
Collection failure MUST remain non-blocking and MUST NOT appear as clean
evidence. Check mode MUST NOT run the command or publish a collected report.
No service settings, SSH policy or existing Lynis acceptance gate may change.

#### Scenario: Available analyzer and failed analyzer

- **WHEN** the analyzer succeeds, returns nonzero or cannot start
- **THEN** the report preserves the observed result and the default audit continues

#### Scenario: Check mode

- **WHEN** the explicit audit runs in check mode
- **THEN** no analyzer execution or collected isolation report is produced
