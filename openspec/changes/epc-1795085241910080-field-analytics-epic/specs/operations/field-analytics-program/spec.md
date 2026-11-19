## Purpose

Define the ordering and acceptance rules that make the field analytics program deliver correct network, blocking, client-connection and VPN-health analytics.

## ADDED Requirements

### Requirement: REQ-PROGRAM-ORDER — Child changes respect dependencies

The program MUST keep these `blocked_by` edges: D2 on D1; D4 on D1 and D3; D5 on D2 and D3; D7 on D2, D4, D5 and the RIPDPI client work.

#### Scenario: Dependent starts early

- **WHEN** an operator starts D2 while D1 is not done
- **THEN** `./taskctl ready` does not list D2 and `./taskctl validate` records the open blocker

### Requirement: REQ-PROGRAM-PRIVACY — Analytics stay anonymous and aggregated

Every child change MUST NOT introduce an IP address, device or user ID, subscription token, hostname other than `server_ref`, or a timestamp finer than one hour into a client report, a metric label or a log line.

#### Scenario: Privacy review of a child

- **WHEN** a child change reaches review
- **THEN** its verification file names the test that rejects each forbidden field

### Requirement: REQ-PROGRAM-ACCEPT — The chain is proven end to end

The program MUST NOT close until D7 shows, with a real client, that a blocked protocol is classified by stage, ingested, alerted, marked degraded in the bundle and failed over.

#### Scenario: Protocol blocked on staging

- **WHEN** one protocol is blocked with DROP or RST on a staging node
- **THEN** the D7 verification records the client classification, the ingested report, the fired alert, the degraded bundle health and the client failover
