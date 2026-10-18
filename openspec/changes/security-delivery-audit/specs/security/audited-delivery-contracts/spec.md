## Purpose

Repair confirmed security, recovery and delivery failures without changes to live infrastructure or unrelated protocol behavior.

## ADDED Requirements

### Requirement: REQ-AUDIT-AGE-DATA-KEY — Compromise recovery

Recovery guidance MUST remove compromised recipients, rotate the SOPS data key, and only then rotate application credentials.

#### Scenario: Compromise recovery failure boundary

- **WHEN** an age identity or sufficient recovery shares are compromised
- **THEN** the documented recovery prevents the prior data key from decrypting replacement credentials

### Requirement: REQ-AUDIT-AGE-RECIPIENT — Hardware identity selection

Hardware enrollment MUST resolve the selected recipient from supported plugin output without generating a replacement during resume.

#### Scenario: Hardware identity selection failure boundary

- **WHEN** a generated identity contains a commented recipient
- **THEN** enrollment selects that same hardware identity and preserves the existing identity file

### Requirement: REQ-AUDIT-AGE-MIGRATION — Additive migration

Hardware migration MUST preserve existing recipients until independently verified retirement, use its explicit config, and fail on unsuccessful updates.

#### Scenario: Additive migration failure boundary

- **WHEN** a selected document cannot be updated or verified
- **THEN** the command fails and retains prior recoverable ciphertext

### Requirement: REQ-AUDIT-RESTIC-GENERATION — Backup recovery generations

Password-change guidance MUST distinguish wrapping changes from master-key compromise and MUST retain the prior repository until the new generation passes restore verification.

#### Scenario: Backup recovery generations failure boundary

- **WHEN** a replacement backup or restore fails
- **THEN** the previous repository and remote generation remain available

### Requirement: REQ-AUDIT-STATE-PUBLICATION — Complete state backups

State backup MUST publish a final snapshot name only after encryption succeeds and MUST remove only its own incomplete staging file.

#### Scenario: Complete state backups failure boundary

- **WHEN** encryption is interrupted
- **THEN** recovery selection sees only previously complete snapshots

### Requirement: REQ-AUDIT-HTTP-ORIGIN — Authenticated origin confinement

The three audited HTTP clients MUST refuse redirects and notification delivery MUST require a valid HTTPS origin.

#### Scenario: Authenticated origin confinement failure boundary

- **WHEN** an authenticated endpoint redirects to another origin or HTTP
- **THEN** no credential reaches the redirect destination

### Requirement: REQ-AUDIT-SUB-PUBLICATION — Atomic subscription documents

Subscription issuance MUST publish payload bytes and expiry as one atomic document and readers MUST observe a complete old or new generation.

#### Scenario: Atomic subscription documents failure boundary

- **WHEN** publication fails or a reader races refresh
- **THEN** the reader never receives partial bytes or mixed payload and expiry

### Requirement: REQ-AUDIT-HY-EXTRAS — Complete multi-host metadata

Bundle emission MUST retain Hysteria extras for every selected outbound tag independent of host order.

#### Scenario: Complete multi-host metadata failure boundary

- **WHEN** multiple Hysteria hosts are selected
- **THEN** each emitted Hysteria outbound has its exact metadata entry

### Requirement: REQ-AUDIT-HY-COMPATIBILITY — Qualified recipient admission

RIPDPI export MUST refuse Hysteria port hopping until the consumer supports the complete profile.

#### Scenario: Qualified recipient admission failure boundary

- **WHEN** the selected RIPDPI profile enables port hopping
- **THEN** export refuses before publication and official recipient behavior remains unchanged

### Requirement: REQ-AUDIT-BUNDLE-SEMANTICS — Semantic bundle admission

Bundle validation MUST reject invalid canonical keys, endpoints, address ranges, junk ranges and calendar expiry while retaining the existing wire schema.

#### Scenario: Semantic bundle admission failure boundary

- **WHEN** a shape-valid bundle contains invalid protocol values
- **THEN** validation returns a categorical failure without exposing credential values

### Requirement: REQ-AUDIT-ALERT-ENVIRONMENT — Consistent alert scope

Expected-target alerts MUST use the same configured environment authority as the finite-silence gateway.

#### Scenario: Consistent alert scope failure boundary

- **WHEN** a scoped maintenance silence matches a generated alert
- **THEN** its exact environment and target matchers agree

### Requirement: REQ-AUDIT-TELEGRAM-FLOOD — Bounded flood control

Telegram delivery MUST honor the official JSON retry_after without an early retry or unbounded webhook work.

#### Scenario: Bounded flood control failure boundary

- **WHEN** flood wait exceeds the current request budget
- **THEN** delivery returns a retryable failure or retains a bounded cooldown instead of retrying early

### Requirement: REQ-AUDIT-SSH-HYBRID — Supported SSH key agreement

The recoverable SSH transaction MUST consistently admit a supported hybrid KEX with a compatible classical fallback across rendering, ownership and verification.

#### Scenario: Supported SSH key agreement failure boundary

- **WHEN** the managed OpenSSH supports the baseline hybrid
- **THEN** the effective policy offers it and recovery remains available

### Requirement: REQ-AUDIT-INVENTORY-ENCODING — Portable typed inventory

Inventory rendering MUST preserve one complete typed host line when its base64 encoder uses CRLF. Bootstrap parsing MUST retain its existing host and lifecycle checks.

#### Scenario: CRLF encoder at the bootstrap boundary

- **WHEN** a host record contains listener or topology data from a CRLF-producing base64 encoder
- **THEN** the renderer removes transport line endings and bootstrap reads the original typed label from one host line
