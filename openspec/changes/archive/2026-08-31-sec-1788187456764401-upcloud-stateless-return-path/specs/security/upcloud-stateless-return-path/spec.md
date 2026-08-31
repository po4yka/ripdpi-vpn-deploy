## Purpose

Preserve required server-initiated traffic when the UpCloud Public & Utility
firewall is enabled, without weakening SSH or public-listener boundaries.

## ADDED Requirements

### Requirement: REQ-UPF-ACTIVATION — Provider firewall activation is explicit and phased

The UpCloud server MUST keep its provider firewall disabled by default. An
operator MAY enable it only after the exact node has passed strict SSH and guest
stateful-firewall verification. Enabling the provider firewall MUST be an
in-place update, not a server replacement.

#### Scenario: Fresh staging node is created

- **WHEN** the UpCloud root is planned without an explicit activation input
- **THEN** the server is created with the provider firewall disabled while the
  complete ruleset is still managed for later promotion.

#### Scenario: Verified staging node is promoted

- **WHEN** an operator explicitly enables the provider firewall after guest
  verification
- **THEN** Terraform plans only the activation update and preserves the server,
  storage, network identities, SSH allowlist and listener contract.

### Requirement: REQ-UPF-RETURN — Return traffic has a complete dual-stack matrix

The managed ruleset MUST accept inbound TCP and UDP packets destined to the
configured Linux ephemeral client-port range for both IPv4 and IPv6 before the
terminal drops. It MUST also accept DHCPv4 server-to-client UDP 67 to 68 and
DHCPv6 server-to-client UDP 547 to 546 so initial network configuration is not
silently blocked. The ruleset MUST explicitly accept outbound traffic so it
does not depend on mutable account defaults. The ephemeral range MUST be
explicit, ordered, bounded to 1024..65535 and have start less than or equal to
end.

#### Scenario: Server initiates an arbitrary TCP or UDP flow

- **WHEN** the remote peer returns packets to the server's configured ephemeral
  client port over IPv4 or IPv6
- **THEN** the provider rule accepts the packet before the family-specific
  default drop, while the guest stateful firewall remains responsible for
  rejecting unsolicited traffic.

#### Scenario: Invalid return range is configured

- **WHEN** the range is privileged, reversed or above 65535
- **THEN** Terraform refuses the plan before provider access.

### Requirement: REQ-UPF-BOUNDARY — Administrative and listener exposure stays narrow

The change MUST NOT add a world-readable SSH rule or a new public listener.
Return-path rules MUST target only the reviewed ephemeral range or exact DHCP
client ports. The existing typed public-listener contract and both terminal
family drops MUST remain present.

#### Scenario: Return-path support is enabled

- **WHEN** the complete firewall ruleset is rendered
- **THEN** SSH remains limited to `allowed_ssh_cidrs`, public listeners equal
  the typed contract, and no generic accept rule appears after the terminal
  drop.

### Requirement: REQ-UPF-STAGING — Promotion and rollback use isolated live evidence

Before production adoption, an authorized isolated UpCloud node MUST prove
cloud-init package bootstrap, DNS, outbound TCP and UDP, strict SSH and required
public listeners with the provider firewall disabled and again after in-place
activation. Failure MUST stop promotion; rollback disables the provider
firewall through Terraform and rechecks SSH. Cleanup MUST delete only the exact
manifest-bound server, root storage and Terraform-owned rules, then verify
provider absence before the 47-hour hard deadline.

#### Scenario: Post-activation network check fails

- **WHEN** any required outbound, listener or strict SSH probe fails after
  activation
- **THEN** production promotion is refused, the provider firewall is disabled
  on the same staging node, and exact-resource cleanup remains mandatory.
