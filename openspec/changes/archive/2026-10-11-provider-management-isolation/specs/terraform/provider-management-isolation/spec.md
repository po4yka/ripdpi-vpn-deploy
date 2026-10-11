## Purpose

Keep provider management access narrowly scoped and provision replacement nodes
with immutable bootstrap identity and enforced operator plan policy.

## ADDED Requirements

### Requirement: REQ-PMI-POLICY — Apply evaluates the exact saved plan

The Make apply surface MUST evaluate all repository policy namespaces against a
private snapshot of the saved plan and apply that same snapshot only when policy
evaluation succeeds with at least one evaluated rule. Standalone policy checks
MUST use the same evaluator. A default dual-stack UpCloud plan MUST pass the
secondary-IPv4 opt-in policy.

#### Scenario: Safe saved plan is applied

- **WHEN** the saved plan passes all policies with nonzero rule coverage
- **THEN** the same private plan snapshot reaches apply and temporary files are
  removed on exit, including failure.

#### Scenario: Policy or evaluation fails

- **WHEN** a rule denies, the evaluator fails, output is malformed or zero rules run
- **THEN** apply is not invoked and the operator receives a failure.

#### Scenario: Ordinary dual-stack node

- **WHEN** one primary IPv4 and one IPv6 interface are present without secondary-IP opt-in
- **THEN** the secondary-IPv4 policy permits the plan.

### Requirement: REQ-PMI-SSH — Management exposure remains scoped

Every root MUST require a known integer SSH port within 1..65535 and reject zero-prefix management networks and any effective public
TCP singleton or inclusive range containing ssh_port, including legacy listener
resolution. Policy MUST recognize management ports contained in TCP ranges.
UpCloud MUST reject SSH ports inside its stateless return range before either
activation phase. Valid restricted networks and adjacent ranges MUST remain valid.

#### Scenario: Management exposure is configured

- **WHEN** a world network, TCP selector covering SSH or UpCloud return-range collision is supplied
- **THEN** the plan is refused before infrastructure mutation.

#### Scenario: Valid mixed listener contract

- **WHEN** restricted management CIDRs and nonoverlapping TCP listeners are supplied
- **THEN** the plan succeeds, including a UDP listener using the SSH port number.

### Requirement: REQ-PMI-IDENTITY — Creation-time administrator identity is guarded

Username changes on Hetzner, Vultr and Scaleway and administrator key changes on
Vultr and Scaleway MUST require server replacement. The existing prevent_destroy
guard MUST refuse replacement of an existing node. Unchanged identity MUST plan
without replacement. Existing SSH-port and provider-native key guards MUST remain.

#### Scenario: Existing node identity changes

- **WHEN** a guarded administrator input changes after initial creation
- **THEN** the plan reports replacement blocked by prevent_destroy rather than
  publishing a silently divergent management configuration.

#### Scenario: Identity changes while adopting the guards

- **WHEN** an existing legacy node is first planned with the new guards and a
  changed administrator input
- **THEN** planning refuses the divergent identity before mutation; Hetzner also
  protects edits to the server name embedded in its bootstrap key name.

#### Scenario: Existing identity is unchanged

- **WHEN** all creation-time administrator inputs remain unchanged
- **THEN** the existing node continues to plan normally.

### Requirement: REQ-PMI-HETZNER — New nodes use current types and boot protection

Hetzner MUST accept the reviewed cx23, cx33, cpx22 and cpx32 types and reject the
four retired types. The server MUST own its firewall attachment at creation.
Migration MUST forget the former attachment resource without deleting or
detaching it, and MUST preserve existing server and firewall identities.

#### Scenario: Fresh node is planned

- **WHEN** a current approved type and safe management contract are supplied
- **THEN** the server creation references the provider firewall before boot.

#### Scenario: Attachment ownership migrates

- **WHEN** state contains the former standalone attachment
- **THEN** its migration action forgets it without a delete operation and the
  server assumes attachment ownership without an unprotected interval.

#### Scenario: Retired type is supplied

- **WHEN** a private input still names a retired server type
- **THEN** validation refuses it and documentation directs an explicitly reviewed
  disposable-node migration rather than an automatic live resize.

### Requirement: REQ-PMI-ADAPTER — Vultr resource inputs follow provider contracts

Vultr firewall resources MUST translate canonical hyphen-separated port ranges
to colon-separated provider values without changing listener outputs or resource
keys. Singleton ports MUST remain unchanged. Enabled provider backups MUST
include one daily schedule at 03:00 UTC; disabled backups MUST have no schedule.

#### Scenario: Range and singleton listeners are planned

- **WHEN** valid TCP and UDP singleton/range listeners are supplied
- **THEN** both IPv4 and IPv6 resource plans use the appropriate provider syntax
  and canonical listener outputs retain their original values.

#### Scenario: Backup opt-in is changed

- **WHEN** enable_backups is true or false
- **THEN** the plan contains respectively enabled backups with one valid daily
  schedule or disabled backups without a schedule block.

### Requirement: REQ-PMI-LISTENERS — Listener numbers are integers and legacy tests exercise legacy mode

Every root MUST reject fractional public singleton and legacy XHTTP port inputs
while preserving valid integer bounds and explicit-listener precedence. Legacy
XHTTP collision regressions MUST select legacy mode and observe deduplication of
the effective rule set, including absence of the previous XHTTP TCP port.

#### Scenario: Fractional listener port is supplied

- **WHEN** a TCP/UDP singleton or legacy XHTTP port contains a fraction
- **THEN** input validation refuses it before provider mutation.

#### Scenario: Legacy XHTTP collides with TCP 443

- **WHEN** explicit listeners are empty, legacy mode is enabled and XHTTP is 443
- **THEN** the effective firewall has one TCP 443 listener and no old TCP 8443
  listener, while UDP 443 remains valid.

### Requirement: REQ-PMI-SCALARS — Bootstrap strings remain scalar YAML data

Shared cloud-init MUST encode administrator and public-key scalars and complete
metadata file content so punctuation and newline characters cannot change the
YAML document structure. The fixed synthetic CI renderer MUST preserve the same
parsed values as real Terraform rendering, including metadata's trailing newline.
Null bootstrap strings MUST remain refused rather than becoming JSON/YAML null.

#### Scenario: Key comments or metadata contain YAML punctuation

- **WHEN** supplied strings contain colon-space, quotes, backslashes or newlines
- **THEN** YAML parsing preserves the supplied scalar values and original
  top-level bootstrap structure.

#### Scenario: A bootstrap scalar is null

- **WHEN** a username, public key or metadata label is null
- **THEN** rendering fails before infrastructure mutation, preserving the original
  non-null string contract.

### Requirement: REQ-PMI-P2-DELIVERY — P2 source evidence is independent and scoped

P2 repairs MUST retain the reviewed P1 behavior, have positive and refusal-path
credential-free regressions, receive independent review and be added to PR 281
with exact-head hosted results. Existing fixes and withdrawn findings MUST be
reported separately from new changes; no live acceptance MAY be inferred.

#### Scenario: P2 follow-up is delivered

- **WHEN** the remaining actionable P2 repairs are validated and published
- **THEN** PR 281 reports their observed checks and explicitly preserves any
  local, infrastructure, guest or client acceptance gaps.
