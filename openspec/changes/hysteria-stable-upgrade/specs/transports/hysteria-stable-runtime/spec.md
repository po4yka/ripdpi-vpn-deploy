## Purpose

Provide observable, testable guarantees for upgrade hysteria with validated congestion and udp resource profiles across accepted inputs, successful operation, failure and retained authority.

## ADDED Requirements

### Requirement: REQ-PROTO-HY-VERSION — Select an exact eligible stable runtime and compatible clients

The implementation MUST Hysteria upgrades MUST bind a stable non-prerelease release tag to refreshed publication metadata, architecture asset digests and known reachable critical/high advisory status. Production promotion MUST require at least 48 hours since publication and a completed separately authorized 48-hour staging soak. Exact supported client parser versions MUST be refreshed and validated without automatic latest tracking.

#### Scenario: Eligible stable candidate and supported parser

- **WHEN** the candidate release and clients satisfy reviewed metadata, digests, compatibility and staging eligibility
- **THEN** every generator and runtime consumer selects the same exact inputs and positive native parsing and authenticated traffic pass

#### Scenario: Changed hash, prerelease, advisory or insufficient age

- **WHEN** an asset digest changes, the channel is prerelease, a reachable blocking advisory is present or eligibility is incomplete
- **THEN** publication or promotion refuses without weakening checks or replacing the current ready runtime

### Requirement: REQ-PROTO-HY-TUNING — Render typed congestion and resource profiles

The implementation MUST Supported congestion, bandwidth, receive-window and baseline UDP-buffer settings MUST have one typed bounded contract, exact-version parser validation and explicit server/client coordination. TCP BBR settings MUST NOT be represented as QUIC congestion proof, and unsafe or unsupported tuning MUST reject before publication.

#### Scenario: Validated technical resource profile

- **WHEN** a supported congestion/resource profile is selected for a controlled technical path
- **THEN** server and client use the intended supported settings and sustained authenticated traffic stays within declared memory and descriptor bounds

#### Scenario: Unsupported algorithm or excessive resource value

- **WHEN** a setting is absent from the exact runtime API or exceeds configured bounds
- **THEN** schema or native validation refuses and mandatory hardening and prior complete settings remain intact

### Requirement: REQ-PROTO-HY-MEASURE — Measure positive data-plane and resource behavior

A proposed tuning profile MUST be accepted only with observed authenticated TCP UDP and DNS delivery, throughput, latency, reconnect, receive-drop and multiple-client fairness evidence against the baseline under the same controlled path. Missing measurements MUST remain explicit rather than being replaced by render or peak-speed claims.

#### Scenario: Baseline and candidate comparison

- **WHEN** baseline and proposed profiles run on the same bounded loss, latency and packet-size path
- **THEN** both function and their measured resource and delivery results identify the trade-off without claiming unobserved superiority

#### Scenario: Drop or fairness regression

- **WHEN** the candidate causes receive drops, sustained transfer failure or unacceptable resource/fairness regression
- **THEN** the candidate remains in staging or is rejected and baseline remains available

### Requirement: REQ-PROTO-HY-UPGRADE — Activate and compensate the complete runtime upgrade

A pin-only upgrade MUST cause the running Hysteria process to adopt the exact selected binary with production-equivalent TLS, Salamander and owned port hopping. Failed startup or adoption MUST preserve or restore prior complete binary, config, credentials and service readiness; unchanged convergence MUST be idempotent and diagnostics private.

#### Scenario: Warm upgrade and unchanged repeat

- **WHEN** the binary pin changes while private configuration is unchanged and convergence repeats
- **THEN** the live native process adopts the candidate, secure authenticating clients continue to work, and the subsequent unchanged run does not restart

#### Scenario: Candidate startup or redirect regression

- **WHEN** candidate runtime activation fails or hopped traffic fails while base traffic passes
- **THEN** promotion fails, prior complete ready runtime is restored and unrelated outbound UDP remains unchanged
