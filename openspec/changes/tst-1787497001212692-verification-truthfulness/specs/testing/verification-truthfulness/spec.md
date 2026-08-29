## Purpose

Verification tooling tells the truth: it passes for every supported host class exactly when deployed state matches intent, tests idempotence where the repo declares it contractual, documents scenarios as they actually run, and machine-checks first-boot listen-surface guarantees.

## ADDED Requirements

### Requirement: REQ-VERIFY-HOSTCLASS-GATING — Transport verification MUST honor host class

Transport assertions in verify and smoke tooling MUST skip on hosts where site.yml deliberately skips deployment (subscription-only), using the same contract as sibling tasks. This includes transport configuration validation, service/interface state, listeners and P1 DNS/address prerequisites. Shared bootstrap, manifest, firewall, SSH and sysctl verification MUST remain active on subscription-only hosts. Smoke gating MUST cover transport credential lookup, temporary resource creation and cleanup as well as probes, so a subscription-only host needs no transport credentials and invokes no smoke clients.

#### Scenario: verify on subscription-only host

- **WHEN** `make verify` runs against a subscription-only host
- **THEN** transport assertions skip rather than fail on undeployed services

### Requirement: REQ-DRIFT-FULL-IDENTITY — Drift checks MUST compare full source identity

Source-drift parity MUST compare both the deployable digest and the source revision of the deployed manifest.

#### Scenario: digest-matching manifest from another commit

- **WHEN** a node's manifest was written by a different commit with a colliding digest scope
- **THEN** the drift gate fails on the revision mismatch

### Requirement: REQ-VERIFY-DEPLOYED-LISTENERS — Verification MUST assert deployed listeners at their configured ports

Listener assertions MUST use configured port variables and MUST cover fallback listeners that deploy opens in the firewall when enabled.

#### Scenario: non-default hysteria port

- **WHEN** verify runs on a host with a custom hysteria_port
- **THEN** the UDP assertion targets the configured port and passes against the real listener

#### Scenario: enabled fallback ports

- **WHEN** fallback listeners are deployed and firewall-opened
- **THEN** verify asserts their presence instead of ignoring them

### Requirement: REQ-IDEMPOTENCE-WHERE-DECLARED — Declared integration scenarios MUST test idempotence

Full-stack molecule sequences MUST include an idempotence phase; per-role scenarios without one MUST document the omission where the contract expects it.

#### Scenario: second converge of full stack

- **WHEN** the full-stack scenario converges twice
- **THEN** the second run reports zero changes or the scenario fails naming the offending task

#### Scenario: published full-stack prerequisites

- **WHEN** the published scenario is invoked from its documented `ansible/` working directory
- **THEN** dependency paths resolve to the current checkout's pinned requirements and its explicit provider listener contract matches the runtime manifest rendered from the scenario inputs
- **AND** a missing contract or mismatched declared port fails validation before convergence; local input checks alone do not establish second-converge idempotence

#### Scenario: repeat converge of the Xray role scenario

- **WHEN** the default Xray Molecule scenario converges twice using its synthetic release binary
- **THEN** fixture setup preserves the runtime role's symlinks and the second converge reports zero changes
- **AND** the explicit idempotence phase executes the real converge without suppressing changed results

### Requirement: REQ-SCENARIO-RUNS-ROLE — Molecule scenarios MUST exercise role task code

Scenarios validating a role MUST execute the role itself (against stubbed externals) rather than re-implementing its render logic in the converge play.

#### Scenario: regression in amneziawg task logic

- **WHEN** a change breaks amneziawg tasks/main.yml behavior
- **THEN** the amneziawg molecule scenario fails instead of passing on hand-rendered templates

#### Scenario: synthetic AWG build inputs exercise real role ownership

- **WHEN** the scenario supplies explicitly synthetic local Git sources and no-TUN tools
- **THEN** the unchanged role clones and verifies the fixture commits, builds and installs the tools, writes its own receipts, renders configuration and converges its systemd units
- **AND** preparation does not preinstall those outputs, external Git fallback is denied, and the second converge reports zero changes
- **AND** the evidence is limited to role orchestration, not an upstream build or working AWG tunnel

### Requirement: REQ-TESTING-DOCS-REALITY — Test documentation MUST match observed sequences

docs/TESTING.md coverage rows MUST describe what scenarios actually run and MUST list every role with a scenario or a documented skip.

#### Scenario: matrix audit

- **WHEN** each TESTING.md row is compared to its molecule.yml
- **THEN** descriptions match observed test sequences and no role is silently absent

### Requirement: REQ-SINGLE-SSH-LISTENER — The single SSH listener guarantee MUST be machine-checked

Post-converge verification MUST assert that effective sshd configuration exposes exactly one listener per host, guarding socket/service reconciliation.

#### Scenario: socket holding a stale port

- **WHEN** an image leaves ssh.socket listening on the packaged port alongside the configured one
- **THEN** verify fails naming both listeners
