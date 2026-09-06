## Purpose

Define the observable safety contract for a reviewed, disabled-by-default network exposure denylist gate.

## ADDED Requirements

### Requirement: REQ-ANS-1786277767052693-001 — Disabled mode preserves firewall output

The deployment system MUST leave rendered firewall policy and managed-host state unchanged when the denylist gate is disabled.

#### Scenario: Default render remains unchanged

- **GIVEN** the repository default configuration and no reviewed feed artifact
- **WHEN** an operator renders or applies the normal site playbook
- **THEN** the resulting firewall input and managed rules MUST be equivalent to the pre-feature output

### Requirement: REQ-ANS-1786277767052693-002 — Policy input is validated before use

The deployment system MUST validate feed metadata and policy intent before render or apply, MUST keep ingress, host-originated egress, and forwarded-traffic decisions distinct, and MUST reject invalid, stale, unsigned, or unreviewed inputs.

#### Scenario: Invalid input fails closed

- **GIVEN** a feed artifact whose schema, review state, digest, signature, or expiry is invalid
- **WHEN** an operator requests render, check mode, or apply
- **THEN** the operation MUST fail before producing deployable rules or changing a managed host

#### Scenario: Traffic directions remain distinct

- **GIVEN** a valid reviewed artifact and policy intent for only one traffic direction
- **WHEN** the role renders its policy plan
- **THEN** no ingress, host-originated egress, or forwarded-traffic decision outside that explicit direction MAY be inferred

#### Scenario: External deployment inputs are bound before transport

- **GIVEN** a typed private override, reviewed artifact, and pinned key for an exact inventory selection
- **WHEN** an operator requests check mode, canary, or enforcement
- **THEN** the controller MUST validate, snapshot, and fence every input before SSH or Ansible
- **AND** only the private snapshots MAY reach the selected hosts' canonical variable loaders
- **AND** ambient host variables, group variables, plugins, or arbitrary extra vars MUST NOT supply policy authority

### Requirement: REQ-ANS-1786277767052693-003 — Repository fixtures are non-deployable

The repository MUST contain only placeholder feed fixtures and MUST reject committed address ranges, ready-to-load firewall payloads, or provider policy rules in the feature-owned paths.

#### Scenario: Fixture policy blocks deployable data

- **GIVEN** a proposed fixture containing an address range or loadable rule payload
- **WHEN** repository validation runs
- **THEN** validation MUST fail with the offending fixture path and without printing sensitive inventory data

### Requirement: REQ-ANS-1786277767052693-004 — Review output is redacted and non-mutating

Dry-run and log-only modes MUST report only aggregate counts, repository-local source identifiers, policy direction, validation state, and content digest, and MUST NOT change firewall state.

#### Scenario: Dry-run exposes bounded evidence

- **GIVEN** a valid reviewed artifact and log-only policy
- **WHEN** an operator runs the documented dry-run command
- **THEN** output MUST be sufficient to review the policy while omitting address values, host inventory, credentials, and ready-to-apply commands

#### Scenario: Unsafe external input never reaches transport

- **GIVEN** a missing, replaced, linked, writable, malformed, or selection-mismatched override, artifact, or key
- **WHEN** an operator invokes the canonical controller
- **THEN** the operation MUST fail before SSH, Ansible, or a success audit

### Requirement: REQ-ANS-1786277767052693-005 — Promotion and rollback are explicit

The deployment system MUST require explicit operator configuration for log-only, canary, and enforcement modes and MUST define expiry, false-positive monitoring, promotion, and rollback criteria without an automatic feed updater or hidden apply path.

#### Scenario: No implicit promotion

- **GIVEN** a successful dry-run or log-only observation
- **WHEN** no explicit canary or enforcement configuration is committed and approved
- **THEN** the system MUST remain non-enforcing and MUST NOT refresh or apply feed content automatically
