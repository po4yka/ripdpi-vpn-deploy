## Context

Task `SEC-1788187456764401` replaces the unsafe draft PR110 approach. Official
UpCloud documentation states that the Public & Utility firewall is stateless,
rules are evaluated in order, and both directions of a connection must be
allowed. The current root has only inbound allows plus terminal inbound drops.

## Goals / Non-Goals

- Goal: preserve arbitrary server-initiated TCP/UDP flows over IPv4 and IPv6.
- Goal: avoid an unsafe boot interval by making provider activation a separate,
  explicit in-place phase after the guest stateful firewall is verified.
- Goal: retain exact SSH CIDR and public-listener contracts.
- Non-goal: implement a stateful provider firewall, change guest nftables,
  modify production, or merge/rebase PR110.

## Decisions

- Add `enable_provider_firewall`, default `false`, and assign it to
  `upcloud_server.vpn.firewall`. Rules remain declaratively managed while the
  provider edge is disabled so promotion needs only an in-place server update.
- Add `return_ephemeral_port_start` and `return_ephemeral_port_end`, defaulting
  to Linux's canonical `32768..60999`. Validation rejects privileged, reversed
  or invalid bounds.
- Emit four generic return rules: TCP/UDP crossed with IPv4/IPv6, destination
  limited to the configured ephemeral range. Source address and port remain
  unrestricted because VPN forwarding may target arbitrary peer ports.
- Emit exact DHCPv4 and DHCPv6 reply rules. Broad ICMP rules remain unchanged
  because IPv6 neighbor discovery and packet-error delivery require ICMPv6.
- Emit an explicit generic outbound accept. Guest nftables owns reviewed egress
  policy; provider behavior must not depend on an account/UI default.
- Place every return/bootstrap allow before family-specific terminal drops.
  The guest nftables state machine is the unsolicited-packet enforcement layer;
  the provider rule alone is not treated as stateful protection.

## Boundaries and ownership

- Terraform owns provider server activation and provider firewall rules.
- Cloud-init and Ansible own bootstrap and the guest stateful firewall.
- Staging credentials, Terraform state, plan, UUID manifest and evidence remain
  private and outside Git.
- No Makefile or shared CI hunk is needed for the source fix.

## Risks / Trade-offs

- The provider accepts unsolicited packets aimed at the ephemeral range. The
  guest stateful firewall rejects them after convergence; phased activation
  prevents that range from opening before guest protection exists.
- A host with a non-default ephemeral range could lose replies. The range is
  explicit and staging verifies the live kernel value before promotion.
- Provider activation could still disrupt an untested flow. Staging repeats
  DNS, TCP, UDP, SSH and listener checks after activation and rolls back on the
  first failure.

## Migration and rollback

Terraform takes explicit ownership of the server firewall flag. Before the
first apply of this revision to any existing environment, inspect the current
provider state and set the input to that reviewed intent; an externally enabled
firewall must use `true` to avoid an unintended disable.
For staging: plan/create with activation false, converge and verify the guest,
confirm `ip_local_port_range`, apply activation true, then repeat acceptance.
Rollback sets activation false on the same exact server and verifies strict
SSH before guarded destroy.

## Validation strategy

- Native Terraform tests for activation default/opt-in, exact dual-stack rule
  matrix, DHCP, ordering, range validation and retained SSH/listener policy.
- Terraform validate and provider-root plan inspection without apply.
- Repository validation and exact hosted CI.
- Authorized isolated staging proof followed by UUID-bound destroy and provider
  absence/billing verification.
