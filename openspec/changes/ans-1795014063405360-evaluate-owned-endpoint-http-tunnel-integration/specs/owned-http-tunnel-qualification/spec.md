## Purpose

Establish reproducible evidence before admitting a new owned HTTP tunnel endpoint into the deployment stack.

## ADDED Requirements

### Requirement: REQ-OHT-ADMISSION — Reproducible protocol and license review

The qualification MUST pin endpoint and client revisions, record protocol and dependency license obligations, and produce an explicit admit or reject decision. Unknown evidence MUST NOT become a passing result.

#### Scenario: Missing client compatibility evidence

- **WHEN** the endpoint is functional but the intended client has not been exercised
- **THEN** admission remains blocked and no bundle capability is advertised.

### Requirement: REQ-OHT-ISOLATION — Bounded credential-free fixtures

The harness MUST use disposable local credentials, no fleet inventory, no production network changes, bounded timeouts and resource cleanup. It MUST test authenticated TCP, UDP and DNS forwarding, invalid credentials, expired certificates, unavailable HTTP/3 with HTTP/2 fallback and clean shutdown without leaked listeners.

#### Scenario: Authentication failure

- **WHEN** a fixture presents invalid credentials
- **THEN** no destination traffic is forwarded and redacted evidence records rejection.

### Requirement: REQ-OHT-COMPARE — Honest comparative acceptance

The report MUST compare the candidate with the existing baseline using identical controlled payloads, budgets and failure conditions. It MUST distinguish local compatibility from path-specific effectiveness, record unsupported capabilities and rollback, and leave all production toggles unchanged.

#### Scenario: Endpoint is unreachable

- **WHEN** the controlled path rejects the endpoint IP
- **THEN** the outcome is unreachable, not successful allowlist circumvention, and the baseline configuration is unchanged.
