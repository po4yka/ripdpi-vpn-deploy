## ADDED Requirements

### Requirement: REQ-AUDIT-REALM — Isolated Realm TLS

Realm MUST run without Hysteria group privileges and MUST reload its TLS material when that material changes.

#### Scenario: Shared Hysteria TLS

- **WHEN** Realm reuses Hysteria TLS
- **THEN** Realm receives its own certificate and key copies and cannot access Hysteria runtime configuration or loopback services.

### Requirement: REQ-AUDIT-PRIVACY — Private delivery and telemetry

Public nginx logs MUST exclude bearer routes. AWG bundle tags MUST derive from node identity and contain no device name. Probe explanations MUST redact decrypted secret paths.

#### Scenario: A node serves mixed traffic

- **WHEN** an ordinary page and a protected route are requested or a device receives an AWG bundle
- **THEN** the public log excludes the protected route and the AWG endpoint uses a bounded node tag.

### Requirement: REQ-AUDIT-INPUT — Validated operator and service inputs

Operator and deployment inputs MUST enforce safe identities and paths, per-device Hysteria credentials, correct secrets permissions and bounded subscription settings. Subscription retirement MUST remove its owned helpers. An unreadable ASN dataset MUST leave report intake available.

#### Scenario: Invalid input or damaged auxiliary data

- **WHEN** an input fails its authority or format checks or the ASN data is unreadable
- **THEN** the relevant operation refuses unsafe input or report intake continues without the network hint.

### Requirement: REQ-AUDIT-OPERATOR — Complete operator and CI actions

First device enrollment, QR selection, probe collection and Prometheus fixture checks MUST execute their declared behavior.

#### Scenario: Operator action or CI input change

- **WHEN** an operator bootstraps secrets, selects a QR type or makes a matrix probe, or the Prometheus fixture changes
- **THEN** enrollment can create the first complete device, the QR matches the selected format, ordered probe results isolate timeouts, and engine interoperability runs for the fixture change.
