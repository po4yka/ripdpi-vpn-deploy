## Purpose

Ensure deployment security and runtime lifecycle behavior remain consistent across every supported operator entry point.

## ADDED Requirements

### Requirement: REQ-AUDIT-SECRETS — Private diagnostics

The implementation MUST exclude AWG private keys and PSKs from Ansible output and exclude YAML source excerpts from malformed-secret diagnostics.

#### Scenario: Private diagnostics regression

- **WHEN** synthetic secret-bearing inputs reach normalization or parsing failures
- **THEN** neither stdout nor stderr contains those values.

### Requirement: REQ-AUDIT-POLICY — Provider plan enforcement

The implementation MUST evaluate all firewall policy namespaces, reject zero evaluations, account for port intervals and unrestricted sources, distinguish secondary IPv4 from default IPv6, and apply only the validated saved-plan snapshot.

#### Scenario: Provider plan enforcement regression

- **WHEN** a plan opens management ports through a range or default source, or an ordinary dual-stack plan is checked
- **THEN** unsafe exposure is rejected while ordinary dual-stack passes and rejected plans are never applied.

### Requirement: REQ-AUDIT-RUNTIME — Runtime network continuity

The implementation MUST preserve host DNS, enable forwarding for every enabled forwarding workload, allow XHTTP proxy egress under strict policy, implement Hysteria hopping in the firewall layer, and configure optional Hetzner guest addresses before binding.

#### Scenario: Runtime network continuity regression

- **WHEN** a supported profile exercises stub DNS, split-hop forwarding, XHTTP, port hopping or a floating IPv4 listener
- **THEN** the required runtime path is configured without granting unnecessary daemon capabilities.

### Requirement: REQ-AUDIT-LIFECYCLE — Observed service lifecycle

The implementation MUST stop and clean a disabled observability agent, activate changed runtime binaries, apply ingress certificate and authorization updates, and derive maintenance probes from effective enabled services and AWG instances.

#### Scenario: Observed service lifecycle regression

- **WHEN** a service is disabled, upgraded, revoked or maintained under a nondefault profile
- **THEN** the selected state is reconciled and verified without relying on unrelated restarts.

### Requirement: REQ-AUDIT-OPERATORS — Canonical operational entry points

The implementation MUST run all deployment and check-mode callers through the existing controller, preserve explicit secret paths and exact target limits, support fleet zone selection, initialize Terraform before validation, and compare expected versus actual drift.

#### Scenario: Canonical operational entry points regression

- **WHEN** replacement, reconverge, CI, drift or a fresh CLI deployment runs
- **THEN** the intended positive operation works with required proof inputs and unsafe or unbound inputs refuse before provider mutation.

#### Scenario: Automated trusted fresh-node CI

- **WHEN** fresh-node CI runs with its configured trust and enrollment inputs
- **THEN** it establishes pinned public and Tailnet identity and canonical SSH ownership before deployment, without secret Terraform or cloud-init payloads or trust-on-first-use.

### Requirement: REQ-AUDIT-ROLLBACK — Validated runtime restoration

The implementation MUST share the Xray asset-location contract for rotation and rollback and validate rollback configuration before atomic publication with restoration on failed activation.

#### Scenario: Validated runtime restoration regression

- **WHEN** a rollback candidate is invalid or an activation fails
- **THEN** the prior active configuration is preserved or restored and the operation fails explicitly.
