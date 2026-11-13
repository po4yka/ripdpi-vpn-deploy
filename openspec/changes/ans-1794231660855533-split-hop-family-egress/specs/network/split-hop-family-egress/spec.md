## Purpose

On a split-hop Node A, recipient traffic of every family transport must leave through the tunnel that Node B initiated, so the client-facing address never appears as the source of recipient flows, and loss of the tunnel must stop that traffic rather than expose the address.

## ADDED Requirements

### Requirement: REQ-SHF-ROUTE — Family recipient egress uses the tunnel

When `vpn.enable_split_hop_ingress` and `vpn.split_hop_family_egress` are true, Node A MUST route new original-direction IPv4 flows owned by the transport normalizer and direct gateway users, and new forwarded IPv4 originals arriving on every AmneziaWG instance interface, through the split-hop WireGuard interface, source-translated to Node A's tunnel address. Replies to accepted client flows and flows of other host users MUST keep their existing route.

#### Scenario: Recipient request from each family source

- **WHEN** the gateway user, the normalizer user and an AmneziaWG device request a recipient while the tunnel is up
- **THEN** the recipient observes Node B's public address for all three, and an unowned host user still exits from Node A's uplink.

#### Scenario: Strict reverse-path filtering

- **WHEN** baseline sets `net.ipv4.conf.all.rp_filter=1`
- **THEN** tunnel replies with recipient source addresses are still delivered, because the tunnel interface uses loose mode.

### Requirement: REQ-SHF-COEXIST — The boundary coexists with transport-egress

The ingress-only and family split-hop policies MUST pass the transport-egress kernel audit, so the policy MUST NOT mutate packets in any chain reachable from POSTROUTING, while tunnel SYNs from rerouted users and forwarded devices keep an MSS that fits the tunnel MTU.

#### Scenario: Coexistence with the transport-egress boundary

- **WHEN** the ingress-only or family split-hop policy is loaded and transport-egress applies, verifies or rolls back its host policy
- **THEN** the transport-egress kernel audit admits the ruleset, and the recipient observes a tunnel-sized MSS for gateway and device flows.

### Requirement: REQ-SHF-LIVENESS — Liveness proves IPv4-only AWG on a family host

A protocol-liveness policy with `awg_ipv6: ipv4-only` MUST accept the AWG profile when IPv4 delivers through the tunnel with a fresh handshake and every IPv6 attempt is refused by the server's ICMPv6 administratively-prohibited reply. Any other IPv6 failure, and any IPv6 refusal under the default `dualstack` policy, MUST stay a failure.

#### Scenario: Family host refuses device IPv6

- **WHEN** a family-scope Node A rejects forwarded AWG IPv6 and IPv4 succeeds through the tunnel
- **THEN** the runner reports the IPv6 leg as `policy_refused`, an `ipv4-only` policy counts the AWG profile alive, and a `dualstack` policy counts it blocked.

### Requirement: REQ-SHF-FAIL-CLOSED — No uplink fallback

Family recipient originals MUST NOT leave through any interface other than loopback or the tunnel, including while the tunnel is down or its routes are removed. IPv6 originals from the family users and forwarded IPv6 from AmneziaWG interfaces MUST be refused with an administrative-prohibition reply. The canonical firewall MUST enforce the same boundary independently of the split-hop table once the family users exist.

#### Scenario: Tunnel stopped

- **WHEN** PostDown has removed the tunnel routes and the interface is down
- **THEN** gateway, normalizer and device requests fail, and a listener reachable through the uplink records nothing.

#### Scenario: Device IPv6

- **WHEN** an AmneziaWG device sends an IPv6 original in family scope
- **THEN** Node A rejects it before forwarding.

### Requirement: REQ-SHF-IPV4 — Direct gateway selects IPv4 only

In family scope the direct gateway MUST resolve with `UseIPv4` and dial with `ForceIPv4`; outside family scope and on the WARP gateway the existing dual-stack strategies MUST remain.

#### Scenario: Strategy selection

- **WHEN** the gateway configuration renders with and without family scope
- **THEN** only the family direct gateway selects IPv4-only strategies.

### Requirement: REQ-SHF-ADMISSION — Unsafe combinations refuse before mutation

`site.yml` MUST refuse family scope before any host change when the ingress responder is disabled or when Naive, Snell, DNS-Morph, Hysteria realm, WARP outbound or split-hop egress is enabled on the host. The split-hop role MUST refuse a real converge when either family user is absent or AmneziaWG is enabled without instance interfaces. With `vpn.split_hop_family_egress` false, rendered policy MUST equal the existing research scope apart from the reverse-path and MSS repairs.

#### Scenario: Conflicting direct-egress transport

- **WHEN** family scope is requested together with any listed direct-egress transport
- **THEN** the site guard fails and names that toggle.

#### Scenario: Missing transport identity

- **WHEN** the role converges before transport-egress created its users
- **THEN** it refuses with `split-hop-family-authority-missing`.
