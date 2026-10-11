## Purpose

Provide observable, testable guarantees for deliver selectable alternate xhttp endpoints and measured typed tuning across accepted inputs, successful operation, failure and retained authority.

## ADDED Requirements

### Requirement: REQ-PROTO-XAT-ALTERNATE — Selectable delivered alternate endpoint

The implementation MUST When the direct alternate frontend is enabled, the supported selected-device artifact MUST advertise an independently selectable endpoint with the actual listener port and owned TLS hostname. Disabled or invalid alternate inputs MUST NOT produce a fictional endpoint.

#### Scenario: Enabled alternate completes traffic

- **WHEN** a synthetic supported recipient selects the enabled alternate frontend
- **THEN** authenticated transfer succeeds using its correct hostname port and verified certificate

#### Scenario: Disabled or unsupported alternate is not advertised

- **WHEN** the listener is disabled its identity is invalid or the selected engine lacks support
- **THEN** no unusable alternate is exported and existing supported primary delivery remains available

### Requirement: REQ-PROTO-XAT-TYPED — Typed exact-engine mode and tuning contract

The implementation MUST XHTTP mode and advanced tuning inputs MUST come from a reviewed typed allowlist supported by both exact server and recipient engine. Invalid unknown out-of-bound or version-ineligible fields MUST refuse before publication; arbitrary extra JSON is prohibited.

#### Scenario: Supported typed profile renders and forwards

- **WHEN** a reviewed profile is selected on its verified server/client versions
- **THEN** both exact native parsers accept the full artifact and authenticated upload and download complete

#### Scenario: Unsupported tuning refuses safely

- **WHEN** unknown parameters invalid bounds or unsupported versions are selected
- **THEN** validation refuses categorically before replacing accepted server or recipient artifacts

### Requirement: REQ-PROTO-XAT-MEASURED — Measured delivery and truthful endpoint liveness

Each promoted tuning profile MUST have comparative actual-runtime evidence for throughput latency connection/resource bounds idle recovery and reconnect behavior. Existing liveness MUST identify actual endpoint completion and MUST NOT report primary healthy merely because an alternate succeeded.

#### Scenario: Primary outage retains alternate delivery

- **WHEN** the controlled primary path becomes unavailable while alternate remains healthy
- **THEN** the supported client completes alternate traffic and evidence records degraded primary plus the observed alternate identity

#### Scenario: Tuning meets declared bounds

- **WHEN** baseline and candidate run the same bounded large-transfer idle reconnect and constrained-path scenarios
- **THEN** recorded metrics satisfy explicit profile acceptance thresholds without fabricated success or hidden retries

### Requirement: REQ-PROTO-XAT-ROLLBACK — Preserve security privacy and upgrade eligibility

The implementation MUST Feature activation MUST retain destination isolation private selected-device artifacts transport log privacy and accepted-runtime rollback. Failed tuning or upgrade trials MUST restore authenticated baseline delivery. Stable production pins classical P0 behavior and the PQE HOLD guard MUST remain unchanged without a separate reviewed eligibility transition.

#### Scenario: Failed profile trial restores baseline

- **WHEN** a candidate profile fails activation transfer or resource acceptance
- **THEN** the accepted profile is restored and authenticated primary or configured alternate traffic succeeds

#### Scenario: Private and held capability boundaries persist

- **WHEN** synthetic recipient credentials or an ineligible PQE/prerelease control reach export or validation
- **THEN** credentials stay out of diagnostics unaccepted capability stays disabled and normal classical P0 plus supported XHTTP delivery remain usable
