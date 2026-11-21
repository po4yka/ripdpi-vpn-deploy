## Purpose

Define how split-hop ingress traffic behaves while the tunnel to the egress node is down and after the role retires.

## ADDED Requirements

### Requirement: REQ-SPLIT-HOP-DOWN-FORWARD-ERROR — Fail forwarded flows at once

The implementation MUST make a forwarded device flow that the policy routes to the egress node receive an error immediately while the split-hop tunnel is down, and MUST NOT send it through another interface.

#### Scenario: Tunnel stopped

- **WHEN** the split-hop tunnel stops and a device opens a new flow that the policy marks
- **THEN** the device receives an ICMP unreachable error and no packet of the flow leaves by the direct uplink

### Requirement: REQ-SPLIT-HOP-DOWN-LOCAL-REJECT — Fail local frontend connections at once

The implementation MUST reject a new connection of a marked frontend UID while the split-hop tunnel is down, so the frontend gets a connection error instead of a timeout.

#### Scenario: Frontend connect while the tunnel is down

- **WHEN** a frontend process with a marked UID opens a TCP connection while the tunnel is down
- **THEN** `connect` fails within one second and no packet leaves by the direct uplink

### Requirement: REQ-SPLIT-HOP-RETIREMENT-CLEAN — Leave no policy state after retirement

The implementation MUST remove the split-hop routing rule, the kept table content and the reject rule when the role retires.

#### Scenario: Role disabled

- **WHEN** the operator disables split-hop ingress and converges the node
- **THEN** the node has no split-hop `ip rule`, no route in the split-hop table and no split-hop reject rule
