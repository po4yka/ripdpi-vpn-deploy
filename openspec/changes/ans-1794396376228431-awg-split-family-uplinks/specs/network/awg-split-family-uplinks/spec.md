## ADDED Requirements

### Requirement: REQ-ASU-ADMISSION — Each family is admitted on its own named uplink

With `firewall_awg_uplink6_interface` set, AWG admission MUST check the IPv4 route on the IPv4 uplink and the IPv6 route, default route and RA ownership on the named IPv6 uplink, and MUST refuse when either is missing. The IPv6 uplink MUST NOT be inferred from facts and MUST NOT be `lo`, the split-hop tunnel or an AWG instance name.

#### Scenario: Provider with IPv6 on a second NIC

- **WHEN** IPv4 leaves through `eth0`, IPv6 through `eth1`, and `firewall_awg_uplink6_interface` is `eth1`
- **THEN** admission passes; without the variable it refuses with `awg-dualstack-uplink-unavailable`.

### Requirement: REQ-ASU-FORWARD — Forwarding and NAT stay pinned per family

In split mode the forward chain MUST drop AWG IPv4 traffic to or from any interface but the IPv4 uplink, and IPv6 traffic to or from any interface but the IPv6 uplink, before `established,related`; new connections and masquerade MUST be accepted only on the matching family's uplink.

#### Scenario: Split render

- **WHEN** the firewall renders with IPv4 uplink `eth0` and IPv6 uplink `eth1`
- **THEN** every AWG forward and NAT rule carries the matching `meta nfproto` and uplink, and the ruleset passes `nft -c`.

### Requirement: REQ-ASU-COMPAT — Hosts without a separate IPv6 uplink are unchanged

An empty or equal `firewall_awg_uplink6_interface` MUST render the previous ruleset byte for byte, and split-hop family scope MUST keep both families on the tunnel.

#### Scenario: Existing host

- **WHEN** a host leaves the variable empty or sets it to the IPv4 uplink
- **THEN** template snapshots and the rendered ruleset are unchanged.
