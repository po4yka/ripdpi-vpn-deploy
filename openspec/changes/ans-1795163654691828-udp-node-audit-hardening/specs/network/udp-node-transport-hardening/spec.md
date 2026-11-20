## Purpose

Define the public listener, congestion, connection tracking, tunnel MTU, firewall, split-hop egress, unit sandbox and AmneziaWG admission properties that a UDP transport node and its split-hop peer must hold after convergence.

## ADDED Requirements

### Requirement: REQ-HY-TCP-MASQUERADE — The masquerade site answers over TCP

When `hysteria_masquerade_tcp` is true, the Hysteria configuration MUST serve the masquerade site on TCP/443, and on TCP/80 with an HTTPS redirect only when native ACME is not configured. The listener manifest MUST name each enabled port `hysteria-masquerade`. The `vpn-p2-udp` profile MUST enable the input; the role default MUST leave it off.

#### Scenario: UDP profile without native ACME

- **WHEN** the configuration renders with the input enabled and no `hysteria.acme`
- **THEN** the masquerade block has `listenHTTP: ":80"`, `forceHTTPS: true` and `listenHTTPS: ":443"`, and the manifest enables `hysteria-masquerade` on TCP/80 and TCP/443

#### Scenario: Native ACME owns TCP/80

- **WHEN** the configuration renders with the input enabled and `hysteria.acme`
- **THEN** the masquerade block has only `listenHTTPS`, and the manifest enables `hysteria-masquerade` on TCP/443 only

#### Scenario: Provider contract lacks the listeners

- **WHEN** a deploy starts and the provider contract has no `hysteria-masquerade` entry
- **THEN** the listener contract check fails before any host change

#### Scenario: Profile with another TCP/443 owner

- **WHEN** a profile leaves the input at its default
- **THEN** the configuration and the manifest are unchanged

### Requirement: REQ-HY-MASQUERADE-NO-SELF-ORIGIN — The TCP listener does not proxy to itself

With `hysteria_masquerade_tcp`, the role MUST refuse a masquerade origin whose host is the node's own Hysteria server name or ACME domain.

#### Scenario: Origin names this listener

- **WHEN** the masquerade origin host equals the ACME domain of the node
- **THEN** the role fails before it installs a configuration

### Requirement: REQ-HY-CONGESTION-DEFAULT — Profile-level congestion default

The Hysteria configuration MUST use `hysteria.resource_profile` when the secrets document states it, and `hysteria_resource_profile_default` otherwise. The role default MUST be `bandwidth-capped` and the `vpn-p2-udp` profile MUST set `bbr-conservative`.

#### Scenario: UDP profile without a stated profile

- **WHEN** the secrets document states no resource profile on a `vpn-p2-udp` node
- **THEN** the configuration selects BBR with the conservative profile and ignores client bandwidth

#### Scenario: Stated profile

- **WHEN** the secrets document states `bandwidth-capped`
- **THEN** the configuration has no congestion block

### Requirement: REQ-CONNTRACK-BUDGET — Explicit connection tracking budget

The baseline sysctl policy MUST set `net.netfilter.nf_conntrack_max`, `net.netfilter.nf_conntrack_buckets`, `net.netfilter.nf_conntrack_udp_timeout` and `net.netfilter.nf_conntrack_udp_timeout_stream` from role inputs, as optional keys. The role MUST load `nf_conntrack` before it applies the policy on a host that is not a container, and MUST make the module load before `systemd-sysctl` at boot. `fs.file-max` MUST be 2097152.

#### Scenario: Node with one gibibyte of memory

- **WHEN** the baseline role converges the node
- **THEN** the running kernel reports a connection tracking maximum of 131072

#### Scenario: Container without kernel modules

- **WHEN** the baseline role converges a container
- **THEN** the module load task is skipped and an unavailable connection tracking key does not fail convergence

### Requirement: REQ-AWG-MSS-MTU — Tunnel MTU default and MSS clamp

The AmneziaWG MTU default MUST be 1280 in the role, in transport admission and in the firewall fallback. For every AmneziaWG instance the forward chain MUST, before the established accept, set the TCP MSS of SYN packets from the instance to the instance MTU minus 40 for IPv4 and minus 60 for IPv6, and of SYN packets to the instance to the route MTU.

#### Scenario: Instance without a stated MTU

- **WHEN** the firewall renders for an instance that states no MTU
- **THEN** the clamp sizes are 1240 and 1220

#### Scenario: Device with an older, larger MTU

- **WHEN** a device configured for 1420 opens a TCP connection through an instance at 1280
- **THEN** both peers receive an MSS that fits 1280

### Requirement: REQ-DHCPV4-REPLY — Scoped DHCPv4 reply accept

The input chain MUST accept UDP from port 67 to port 68 over IPv4 on the observed IPv4 default-route interface before the established accept, and MUST omit the rule when no such interface is known. The live listener verifier MUST admit at most one rule of exactly this shape, never on the loopback or Tailnet interface, and MUST still refuse any other accept of UDP/68.

#### Scenario: Reply to a broadcast request

- **WHEN** a DHCP server answers a rebinding request
- **THEN** the reply is accepted on the uplink

#### Scenario: Unscoped accept

- **WHEN** the live ruleset accepts UDP/68 with another source port, family or twice
- **THEN** the verifier reports a violation

### Requirement: REQ-SPLIT-HOP-EGRESS-DEFAULTS — Split-hop egress uplink and peer port

An empty `split_hop_egress.forward_iface` MUST resolve to the observed IPv4 default-route interface and an empty `split_hop_egress.peer_listen_port` to `split_hop_ingress_listen_port`, in the NAT policy, the tunnel configuration, the policy shape check and the firewall. Explicit values MUST win.

#### Scenario: Provider image with another uplink name

- **WHEN** the default-route interface is `enp1s0` and the defaults are empty
- **THEN** NAT and the forward accept name `enp1s0`

### Requirement: REQ-SPLIT-HOP-EGRESS-BOUNDARY — Split-hop egress destination boundary and loader sandbox

The forward chain MUST drop packets from the split-hop interface to `firewall_awg_destination_deny_v4` before the forward accept. The policy loader unit MUST stay active after exit and MUST run with the capability bounding set `CAP_NET_ADMIN` and the hardening floor of the ingress loader.

#### Scenario: Loader after boot

- **WHEN** the loader has installed the policy
- **THEN** the unit reports active, and a failed load reports failed

#### Scenario: Recipient requests a metadata address

- **WHEN** a packet from the split-hop interface has a link-local or private IPv4 destination
- **THEN** it is dropped and counted

### Requirement: REQ-AWG-UNIT-SANDBOX — AmneziaWG unit sandbox

`awg-quick@.service` MUST set `MemoryDenyWriteExecute=yes` and `SystemCallFilter=@system-service`, and MUST keep `CAP_NET_ADMIN` as its only capability.

#### Scenario: Rendered unit

- **WHEN** the unit template renders
- **THEN** both directives are present with the existing hardening floor

### Requirement: REQ-AWG-PUBLISHED-SHAPE — Partial published shape is refused on production

Production admission MUST refuse an AmneziaWG instance whose `jc`, `jmin` and `jmax` equal the published set, and an instance whose `s1` and `s2` equal the published set. The shape generator MUST NOT return such a shape. Staging and fixtures MUST keep accepting the published set.

#### Scenario: One value of the set changed

- **WHEN** a production instance has the published set with a different `s2`
- **THEN** admission refuses the instance with the migration instruction

#### Scenario: Junk and padding both differ

- **WHEN** a production instance differs from the published set in one junk value and one padding value
- **THEN** admission accepts it

### Requirement: REQ-COHORT-FINGERPRINT-INPUT — Fingerprint input completeness

The cohort fingerprint MUST use `awg-3.1-ranges-v1` for an absent `wire_profile`, MUST refuse a parameter set without any of `jc`, `jmin`, `jmax`, `s1`, `s2`, `h1` to `h4`, and MUST return the unchanged value for a complete parameter set.

#### Scenario: Absent wire profile

- **WHEN** the golden parameters are passed without `wire_profile`
- **THEN** the result equals the golden fingerprint

#### Scenario: Absent header value

- **WHEN** a parameter set has no `h4`
- **THEN** the function raises an error and the command exits with status 2 and prints no fingerprint
