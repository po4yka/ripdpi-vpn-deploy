## Purpose

Provide observable, testable guarantees for commit transport runtimes only after complete configuration and readiness acceptance across accepted inputs, successful operation, failure and retained authority.

## ADDED Requirements

### Requirement: REQ-PROTO-RTA-CANDIDATE — Validate the complete candidate before selecting it

The implementation MUST Transport upgrades MUST stage exact pinned runtime bytes, required assets, configuration and TLS as one complete candidate. Native configuration validation MUST use the staged runtime and asset authority before active runtime links are changed.

#### Scenario: Complete candidate is accepted

- **WHEN** a valid exact pinned candidate includes all required assets configuration and TLS
- **THEN** native validation succeeds and the candidate becomes eligible for bounded activation

#### Scenario: Second asset or configuration fails

- **WHEN** a required asset download or native candidate validation fails after binary staging
- **THEN** all active links files and running accepted services remain on the preceding generation

#### Scenario: Hysteria staged startup validates actual runtime

- **WHEN** a Hysteria candidate is validated before live publication
- **THEN** its actual staged binary, TLS and configuration MUST complete bounded isolated startup and authenticated readiness; YAML shape alone is insufficient and cleanup uncertainty refuses activation

### Requirement: REQ-PROTO-RTA-ADOPTION — Commit only observed transport adoption

The accepted generation MUST advance only after the selected process has adopted the complete candidate and authenticated positive protocol traffic succeeds within a deadline. Process activity alone MUST NOT satisfy acceptance.

#### Scenario: New generation forwards authenticated traffic

- **WHEN** candidate activation starts the new Xray or Hysteria2 runtime
- **THEN** the observed runtime identity matches the candidate and a synthetic authenticated request completes

#### Scenario: Active but unusable candidate

- **WHEN** the new service is active but certificate loading listener ownership or authenticated forwarding fails
- **THEN** acceptance refuses and compensation restores the previous accepted authority

### Requirement: REQ-PROTO-RTA-RECOVERY — Restore complete authority and recover interrupted activation

The implementation MUST Ordinary failed activation MUST restore exact preceding runtime links required assets private config TLS and relevant unit state. Interrupted publication MUST leave durable bounded recovery intent; unchanged retry MUST reconcile only known owned authority and preserve the prior distinct rollback generation.

#### Scenario: Activation failure restores forwarding

- **WHEN** an accepted generation A is replaced by B and readiness fails
- **THEN** A is restored and authenticated forwarding succeeds before rollback is reported complete

#### Scenario: Interrupted B retries unchanged

- **WHEN** the controller dies between publication adoption and receipt commitment and the same desired B is retried
- **THEN** known state rolls forward or compensates under the same lock; a later unchanged B is idempotent and previous still identifies A

### Requirement: REQ-PROTO-RTA-AUTHORITY — Keep predictive and private authority boundaries

The implementation MUST Check mode MUST inspect trusted state and report intended work without publishing candidates or starting services. Foreign malformed or unsafe recovery records MUST refuse without destructive cleanup, and all configuration and credential authority MUST stay private in files output and process metadata.

#### Scenario: Fresh and existing predictive run

- **WHEN** a normal or upgrade transaction is evaluated in check mode
- **THEN** no active link credential file receipt or process changes and missing future bytes are reported as unverified

#### Scenario: Foreign recovery state and secret-bearing failure

- **WHEN** a recovery path contains a foreign inode or synthetic credential input causes a failure
- **THEN** foreign bytes remain intact and logs argv and environment expose no credential value
