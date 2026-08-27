## Purpose

Require active provider enforcement of the existing UpCloud SSH and public listener rules while preserving narrowly scoped DNS responses, without replacing a node.

## ADDED Requirements

### Requirement: REQ-UPCLOUD-FIREWALL-ACTIVE — Explicit activation

The UpCloud server configuration MUST explicitly require provider firewall activation, and the mock-provider regression MUST reject an omitted or false activation value.

#### Scenario: Configured server has active enforcement

- **GIVEN** a valid UpCloud environment and its public listener contract
- **WHEN** Terraform evaluates the server configuration
- **THEN** the planned firewall activation value is explicitly true.

#### Scenario: Omitted activation is detected

- **GIVEN** the activation setting is removed or changed to false
- **WHEN** the server regression test runs
- **THEN** it fails rather than treating populated firewall rules as activation evidence.

### Requirement: REQ-UPCLOUD-FIREWALL-SAFE-ROLLOUT — Preserve access and identity

The activation change MUST preserve existing SSH CIDRs, listener rules, server identity, SSH port, and credentials. Operators SHALL install the approved management CIDR before enabling enforcement and SHALL reject replacement or unrelated changes in the live plan.

The DNS reply rules SHALL also be present before activation of an existing disabled rule set. The server resource precedes its dependent rules resource; a targeted rules plan is not an ordering guarantee.

#### Scenario: Existing node is activated

- **GIVEN** the approved management rule is installed and rescue media is detached
- **WHEN** the operator reviews the activation plan
- **THEN** activation is the only intended server change and no replacement is accepted.

#### Scenario: Validation or connectivity fails

- **GIVEN** a plan contains unrelated changes or post-activation access cannot be verified
- **WHEN** the operator evaluates rollout completion
- **THEN** the rollout remains incomplete and recovery uses the authorized console without broadening the SSH allowlist or rotating credentials.

### Requirement: REQ-UPCLOUD-DNS-REPLIES — Preserve narrow resolver responses

The firewall MUST accept replies from approved numeric IPv4 resolver addresses over TCP and UDP source port 53, only to the primary public IPv4 and configured guest ephemeral ports. These accepts MUST precede both terminal inbound denies. Invalid or empty resolver sets and invalid port ranges MUST fail before apply.

#### Scenario: DNS replies survive activation

- **GIVEN** two approved resolver addresses and a guest ephemeral port range
- **WHEN** the provider rules are rendered
- **THEN** exactly four reply rules constrain source address, source port, protocol, destination address and destination port range; SSH and public listeners retain their previous scope.

#### Scenario: Secondary address does not widen reply scope

- **GIVEN** a primary and an optional secondary public IPv4
- **WHEN** the provider rules are rendered
- **THEN** every reply rule targets only the primary IPv4.

#### Scenario: Invalid resolver policy fails closed

- **GIVEN** an empty, duplicate, non-IPv4 resolver set or invalid ephemeral port bounds
- **WHEN** Terraform evaluates the module
- **THEN** validation rejects the policy before apply.
