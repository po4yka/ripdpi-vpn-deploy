## Purpose

The effective SSH port stays reachable only through its source-restricted firewall rules, so no public listener in the provider-edge contract may claim that TCP port.

## ADDED Requirements

### Requirement: REQ-SSH-PORT-RESERVED — Public listeners never cover the effective SSH port

Firewall convergence MUST fail before the nftables ruleset is rendered or installed when any TCP entry of `public_listener_contract`, either an exact `port` or a `port_range` that contains it, equals the single effective SSH port reported by `sshd -T`. When an entry sets both, the exact `port` decides, matching the rule the firewall renders, and an entry with neither MUST fail rather than pass. The failure message MUST name every colliding contract listener and the SSH port and MUST NOT print secret values. The check MUST NOT be suppressible by `listener_collision_allowlist`. UDP entries on the same port number MUST NOT trigger the failure. The check MUST also run in check mode so dry runs fail the same way.

#### Scenario: Honeypot configured on the SSH port

- **WHEN** the honeypot is enabled with `honeypot.port` equal to the effective SSH port, so the contract carries `honeypot` on tcp at that port
- **THEN** the firewall role fails before rendering nftables, naming `honeypot` and the SSH port

#### Scenario: TCP port range covers the SSH port

- **WHEN** a TCP contract entry's `port_range` contains the effective SSH port
- **THEN** the firewall role fails naming that listener

#### Scenario: UDP listener shares the port number

- **WHEN** only a UDP contract entry uses the effective SSH port number
- **THEN** firewall convergence proceeds unchanged

#### Scenario: No collision

- **WHEN** no TCP contract entry covers the effective SSH port
- **THEN** firewall convergence proceeds and the rendered ruleset is unchanged

#### Scenario: Rollback

- **WHEN** the change is reverted
- **THEN** firewall convergence returns to the previous behavior with no persisted host state to clean up, because the check only reads `sshd -T` and inventory
