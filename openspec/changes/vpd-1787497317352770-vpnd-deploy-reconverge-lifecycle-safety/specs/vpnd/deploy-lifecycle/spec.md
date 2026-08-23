## Purpose

Deploy-path subcommands must never leave plaintext secrets behind, must scope production applies exactly as targeted, and must not disclose local secret-file locations in operator output.

## ADDED Requirements

### Requirement: REQ-DEPLOY-CLEAN-GUARANTEE — Secrets cleanup runs after failures

When any deploy or reconverge step fails, the cleanup equivalent of `make clean` MUST still be attempted before the command exits, and its own failure MUST NOT mask the original error.

#### Scenario: Failed verify step

- **WHEN** the verify step exits nonzero during deploy
- **THEN** cleanup runs, the decrypted file is removed, and the reported error remains the verify failure

### Requirement: REQ-RECONVERGE-LIMIT-VALIDATION — Strict IPv4 limit targeting

A registry ipv4 used as an ansible limit MUST parse as an IPv4 literal; any other value MUST abort the operation naming the offending host record before any playbook runs.

#### Scenario: Pattern-valued registry entry

- **WHEN** a host record carries `all` or `prod:*` in the ipv4 field
- **THEN** reconverge refuses to run and names that record

### Requirement: REQ-HOST-FLAG-RESOLUTION — Documented registry resolution

doctor and probe MUST resolve --host through the host registry with the same env/provider matching as reconverge and MUST fail for aliases that are absent or belong to another environment.

#### Scenario: Typo alias

- **WHEN** the operator passes --host typo to doctor
- **THEN** the command exits nonzero reporting the alias is not in the registry instead of embedding it silently

### Requirement: REQ-SUMMARY-SECRETS-PATHS — No secret paths in summaries

Pre-execution summaries on deploy paths MUST NOT print sops or decrypted-secrets file paths; they MUST show stable placeholders instead.

#### Scenario: Deploy confirmation panel

- **WHEN** the deploy wizard renders its plan summary
- **THEN** secret-file rows contain placeholders, not filesystem paths
