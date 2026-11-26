## Purpose

Refuse to publish a node address that a filtered-side vantage cannot reach, and keep ICMP out of admission and liveness evidence.

## ADDED Requirements

### Requirement: REQ-ADMIT-REACH — Reachability before publication

The system MUST check TCP and TLS reachability of a new node listener from a filtered-side vantage before any client bundle includes the node address.

#### Scenario: admitted node

- **WHEN** a vantage completes TCP and TLS to the listener
- **THEN** the node address can enter a bundle

#### Scenario: unreachable block

- **WHEN** the check fails and the /24 block of the node is unreachable
- **THEN** admission is refused and the operator message says to recreate the node

#### Scenario: no vantage result

- **WHEN** no vantage is available or the result is missing
- **THEN** admission is refused and never passes silently

### Requirement: REQ-ADMIT-NO-ICMP-ONLY — ICMP is never sole evidence

The system MUST NOT use an ICMP result as the only evidence for admission, liveness or burn decisions.

#### Scenario: ICMP silent but TLS passes

- **WHEN** ICMP gets no reply and TCP and TLS pass
- **THEN** the node is not marked down on ICMP alone

#### Scenario: ICMP replies but TLS fails

- **WHEN** ICMP gets a reply and TCP or TLS fails
- **THEN** the node is not marked up on ICMP alone
