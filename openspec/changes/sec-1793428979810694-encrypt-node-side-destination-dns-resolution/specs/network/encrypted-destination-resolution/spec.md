## Purpose

The host's own lookups must not appear as plaintext DNS on the VPS uplink when systemd-resolved is present, without leaving a host without working DNS, and DNS-Morph's ownership of port 53 stays intact. Recipient destination resolution is covered by the merged loopback forwarder capability and is not restated here.

## ADDED Requirements

### Requirement: REQ-HOST-DOT — Host resolver uses strict DNS over TLS with explicit servers

When the host runs systemd-resolved, baseline MUST install a `resolved.conf.d` drop-in with explicit `DNS=` servers carrying certificate names, `Domains=~.`, `DNSOverTLS=yes`, `LLMNR=no` and `MulticastDNS=no`, restart resolved before dependent roles, and prove one lookup through the encrypted resolver. Check mode MUST change nothing. Strict firewall egress MUST admit TCP/853.

#### Scenario: Fresh host

- **WHEN** baseline converges on a host with systemd-resolved and reachable DoT upstreams
- **THEN** the drop-in exists, resolved restarted once, the proof lookup ran, and a second converge restarts nothing.

#### Scenario: Hosts without resolved

- **WHEN** the host has no `systemd-resolved.service`
- **THEN** baseline writes no drop-in and changes nothing else.

#### Scenario: Strict egress

- **WHEN** the firewall renders `firewall_egress_policy: strict`
- **THEN** the egress chain accepts TCP destination port 853.

### Requirement: REQ-HOST-DOT-COMPENSATION — A failed encrypted-resolver proof is withdrawn, not downgraded

If the proof lookup fails, baseline MUST withdraw the drop-in, restart resolved and fail. It MUST NOT leave a host without working DNS and MUST NOT fall back to plaintext silently.

#### Scenario: Unreachable encrypted upstream

- **WHEN** the proof lookup fails after the drop-in restart
- **THEN** the drop-in is removed, resolved restarts again, and the play fails with a categorical message.

### Requirement: REQ-DNS-MORPH-PORT53 — DNS-Morph port-53 ownership is unchanged

The change MUST NOT bind any new port-53 listener and MUST keep the stub release, deferred restoration and retirement tasks unchanged.

#### Scenario: DNS-Morph enabled

- **WHEN** `vpn.enable_dns_morph_bridge` is true
- **THEN** the resolver round trip (stub release, deferred restore, retirement restore) produces the same resolver symlink states and restart counts as before.
