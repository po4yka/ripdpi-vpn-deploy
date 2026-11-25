## Purpose

Keep the recipient gateway the only receiver of normalizer UDP on its relay address, while the vendor tunnel daemon that shares the WARP namespace address can hold its own underlay socket.

## ADDED Requirements

### Requirement: REQ-PROTO-RDB-RELAY-OWNER — One receiver of normalizer UDP on the relay address

Policy activation MUST refuse with `foreign-relay-owner` when a UDP socket is bound to a gateway relay address and its owner is not that gateway. The only exception is in the WARP namespace: activation MUST admit a root-owned UDP socket on the relay address that is connected to a peer address other than the host side of the namespace link. A socket on a gateway port MUST keep its port-owner refusal.

#### Scenario: Vendor tunnel socket in the WARP namespace is admitted

- **WHEN** the WARP namespace holds a root-owned UDP socket on the relay address that is connected to a public peer, and the tunnel interface is up
- **THEN** namespace policy activation and verification succeed and the tunnel identity is published

#### Scenario: Foreign receiver on the relay address stays refused

- **WHEN** the WARP namespace holds a UDP socket on the relay address that a non-root, non-gateway user owns, or that is unconnected, or that is connected to the host side of the namespace link, or whose peer is unreadable
- **THEN** activation refuses with `foreign-relay-owner` and the accepted policy stays in force

#### Scenario: Host relay address has no exception

- **WHEN** the host holds a root-owned connected UDP socket on the direct gateway relay address
- **THEN** activation refuses with `foreign-relay-owner`
