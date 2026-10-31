## Purpose

Recipient destination names resolved on the node, and the host's own lookups, must not appear as plaintext DNS on the VPS uplink. The normalizer's literal-only gateway contract, the anti-rebinding answer filter and DNS-Morph's ownership of port 53 stay intact.

## ADDED Requirements

### Requirement: REQ-EGRESS-DNS-FORWARDER — Seal the normalizer to the owned loopback forwarder

The production egress context MUST seal the normalizer's resolver to exactly `127.0.0.1` and MUST publish a resolver forwarder port in the kernel policy projection. The owned kernel policy MUST redirect only normalizer-UID port-53 traffic to that port, admit only the normalizer to it, and admit the direct gateway's replies to the redirected flow.

#### Scenario: Production projection

- **WHEN** `transport_egress_config.py` builds the egress context for any enabled profile
- **THEN** the normalizer `resolver.nameservers` is `["127.0.0.1"]`, the policy projection carries `resolver.forwarder_port`, and the rendered policy contains an output NAT redirect for the normalizer UID on `udp`/`tcp` port 53, an admission drop for every other UID on the forwarder port, a normalizer accept for the forwarder port and a gateway reply accept bound to original destination port 53.

#### Scenario: Loopback forwarder is the only loopback nameserver

- **WHEN** a normalizer configuration names any loopback nameserver other than `127.0.0.1`, or a policy projection names a loopback nameserver without a forwarder port, or a forwarder port that collides with a listener, backend or pool
- **THEN** validation refuses before publication.

#### Scenario: Fixture resolvers stay direct

- **WHEN** a policy projection has no forwarder port and names only public literal nameservers
- **THEN** rendering keeps the existing direct port-53 accept rules for the normalizer, so native fixtures with an authoritative peer resolver keep their contract.

### Requirement: REQ-GATEWAY-DOH-ANSWERS — The direct gateway answers the forwarder over DoH with the anti-rebinding filter

The direct private gateway MUST answer the forwarder's A and AAAA queries from Xray's built-in DNS over `https+local://` upstreams that each carry the canonical `unexpectedIPs` set, and MUST drop every other query type instead of forwarding it in plaintext.

#### Scenario: Forwarder answers and filters

- **WHEN** the normalizer resolves a name whose upstream answer mixes a public address with a loopback or private address
- **THEN** the normalizer receives only the public address, a non-A/AAAA query receives no plaintext upstream forward, and the gateway's rendered `dns.servers` use `https+local://` addresses with `unexpectedIPs`.

### Requirement: REQ-FRONTEND-DNS-DOH — Frontend built-in DNS uses DoH outside cascade

The Xray frontend's `dns.servers` MUST use `https+local://` addresses whenever cascade ingress is disabled. With cascade ingress enabled, the servers MUST remain `tcp://` so the queries keep traversing the classifier tunnel.

#### Scenario: Default frontend

- **WHEN** the xray role renders with cascade ingress disabled
- **THEN** every `dns.servers` entry starts with `https+local://`.

#### Scenario: Cascade frontend

- **WHEN** the xray role renders with cascade ingress enabled
- **THEN** `dns.servers` is unchanged from the previous contract.

### Requirement: REQ-HOST-DOT — Host resolver uses strict DNS over TLS with explicit servers

When the host runs systemd-resolved, baseline MUST install a `resolved.conf.d` drop-in with explicit `DNS=` servers carrying certificate names, `Domains=~.`, `DNSOverTLS=yes`, `LLMNR=no` and `MulticastDNS=no`, restart resolved before dependent roles, and prove one lookup through the encrypted resolver. Check mode MUST change nothing. Strict firewall egress MUST admit TCP/853.

#### Scenario: Fresh host

- **WHEN** baseline converges on a host with systemd-resolved and reachable DoT upstreams
- **THEN** the drop-in exists, resolved restarted once, the proof lookup ran, and a second converge restarts nothing.

#### Scenario: Hosts without resolved

- **WHEN** the host has no `systemd-resolved.service`
- **THEN** baseline writes no drop-in and the egress forwarder still resolves recipient destinations without plaintext uplink DNS.

### Requirement: REQ-HOST-DOT-COMPENSATION — A failed encrypted-resolver proof is withdrawn, not downgraded

If the proof lookup fails, baseline MUST withdraw the drop-in, restart resolved and fail. It MUST NOT leave a host without working DNS and MUST NOT fall back to plaintext silently.

#### Scenario: Unreachable encrypted upstream

- **WHEN** the proof lookup fails after the drop-in restart
- **THEN** the drop-in is removed, resolved restarts again, and the play fails with a categorical message.

### Requirement: REQ-DNS-MORPH-PORT53 — DNS-Morph port-53 ownership is unchanged

The change MUST NOT bind any new port-53 listener, MUST keep the stub release, deferred restoration and retirement tasks unchanged, and MUST keep the normalizer resolving through the forwarder when DNS-Morph owns the public port.

#### Scenario: DNS-Morph enabled

- **WHEN** `vpn.enable_dns_morph_bridge` is true
- **THEN** the resolver round trip (stub release, deferred restore, retirement restore) produces the same resolver symlink states and restart counts as before, and the normalizer's redirected port-53 traffic never reaches the public UDP/53 listener.
