## Purpose

Establish reproducible evidence before admitting a new owned HTTP tunnel endpoint into the deployment stack.

## ADDED Requirements

### Requirement: REQ-OHT-ADMISSION — Reproducible protocol and license review

The qualification MUST pin endpoint and client revisions, record protocol and dependency license obligations, and produce an explicit admit or reject decision. Unknown evidence MUST NOT become a passing result. The report MUST name each client it exercised by implementation, revision and platform. The upstream reference client proves protocol compatibility only; RIPDPI client support stays unclaimed until a peer task in the client repository exercises it.

#### Scenario: Missing client compatibility evidence

- **WHEN** the endpoint works with the upstream reference client but no RIPDPI client has been exercised
- **THEN** the report records protocol compatibility only, admission of a bundle capability remains blocked and no bundle capability is advertised.

### Requirement: REQ-OHT-ISOLATION — Bounded credential-free fixtures

The harness MUST use disposable local credentials, no fleet inventory, no production network changes, bounded timeouts and resource cleanup. It MUST test authenticated TCP, UDP and DNS forwarding, invalid credentials, expired certificates, unavailable HTTP/3 with HTTP/2 fallback and clean shutdown without leaked listeners.

#### Scenario: Authentication failure

- **WHEN** a fixture presents invalid credentials
- **THEN** no destination traffic is forwarded and redacted evidence records rejection.

### Requirement: REQ-OHT-COMPARE — Honest comparative acceptance

The report MUST compare the candidate with the existing baseline using identical controlled payloads, budgets and failure conditions. The primary comparison MUST be P1 (nginx + XHTTP direct), the existing HTTP-based transport. It MUST distinguish local compatibility from path-specific effectiveness, record unsupported capabilities and rollback, and leave all production toggles unchanged.

#### Scenario: No benefit over P1

- **WHEN** the candidate matches P1 on every controlled measurement and adds no capability that P1 lacks, such as UDP or DNS forwarding or HTTP/3 behavior
- **THEN** the report states that it adds nothing measurable, rejects admission and leaves the baseline configuration unchanged.

#### Scenario: Endpoint is unreachable

- **WHEN** the controlled path rejects the endpoint IP
- **THEN** the outcome is unreachable, not successful allowlist circumvention, and the baseline configuration is unchanged.
