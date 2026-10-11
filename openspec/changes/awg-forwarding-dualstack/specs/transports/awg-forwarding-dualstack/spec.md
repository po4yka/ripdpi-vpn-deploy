## Purpose

Provide observable, testable guarantees for deliver interface-correct dual-stack amneziawg forwarding and configurable mtu across accepted inputs, successful operation, failure and retained authority.

## ADDED Requirements

### Requirement: REQ-PROTO-AWG-FORWARD — Forward and NAT only effective owned interfaces

Every effective AWG instance, including a nondefault single-instance interface, MUST have its own uplink-scoped forward and NAT rule. Forward policy MUST remain default-drop and unrelated interfaces and tables MUST retain their prior behavior.

#### Scenario: Nondefault interface and two-instance public traffic

- **WHEN** awg7 or two explicitly named effective instances carry authenticated traffic
- **THEN** TCP and UDP exit the approved uplink with instance-addressable NAT counters and both return paths work

#### Scenario: Unapproved interface or cross-instance forwarding

- **WHEN** traffic enters an unowned tunnel or requests a forbidden cross-instance path
- **THEN** new forwarding is denied and unrelated existing host connectivity remains intact

### Requirement: REQ-PROTO-AWG-DUAL — Deliver and authorize both device address families

A profile advertised as dual-stack MUST provision distinct IPv4 and IPv6 device host identities, authorize both at the selected server, and propagate them consistently through enrollment, export, bundle parsing, revocation and liveness. Missing IPv6 prerequisites MUST prevent a dual-stack success claim.

#### Scenario: IPv6-only destination and both return paths

- **WHEN** a dual-stack device connects through the selected instance to IPv4 and IPv6-only controlled targets
- **THEN** bidirectional authenticated TCP UDP and DNS succeed using the allocated source identities

#### Scenario: Missing authorization or uplink family

- **WHEN** the server omits the selected IPv6 prefix or the approved uplink cannot deliver IPv6
- **THEN** validation or traffic acceptance fails explicitly and the profile cannot be marked dual-stack ready

### Requirement: REQ-PROTO-AWG-MTU — Share one validated MTU across server and clients

The effective technical profile MUST expose one bounded MTU contract with deterministic instance precedence. Server configuration, standalone output, RIPDPI bundle and liveness MUST use the same resolved MTU and reject unsupported or inconsistent values before publication.

#### Scenario: Constrained path sustained transfer

- **WHEN** a supported smaller MTU is selected on a controlled path with a lower packet-size ceiling
- **THEN** both families complete sustained TCP and UDP transfers without unresolved packet-size black holes

#### Scenario: Invalid MTU or consumer mismatch

- **WHEN** MTU violates supported bounds or a recipient disagrees with the emitted value
- **THEN** preflight or parser refuses and the prior complete profile remains available

### Requirement: REQ-PROTO-AWG-NOLEAK — Preserve kill-switch and compensating migration

The implementation MUST Connection failure, dual-stack migration and instance revocation MUST preserve IPv4 and IPv6 leak prevention and the prior complete recoverable authority. Disallowed source identities MUST never gain forwarding merely to satisfy a positive test.

#### Scenario: Tunnel failure and revoked device

- **WHEN** the selected tunnel stops or one device is revoked
- **THEN** that device cannot use native IPv4 or IPv6 bypass while unrelated devices remain connected

#### Scenario: Failed complete config activation

- **WHEN** a dual-stack or MTU candidate fails validation or activation
- **THEN** the previous complete addresses routing rules and service configuration remain usable or are restored, with a categorical failure and no mixed generation
