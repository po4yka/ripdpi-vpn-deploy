## Purpose

Preserve guarded destination isolation while establishing TCP connections through
another admitted DNS address when an earlier address cannot connect.

## ADDED Requirements

### Requirement: REQ-PROTO-RDB-FAILOVER — Bounded TCP candidate connection

A named TCP request MUST use one immutable, deduplicated, policy-admitted DNS
snapshot. Candidate order MUST be deterministic and interleave IPv4 and IPv6
while retaining IPv4 as the first family. At most eight candidates and at most
two simultaneous gateway controls MUST be attempted under one connect deadline;
starting a later attempt MUST NOT reset that deadline. Per-attempt expiry MUST
allow later admitted candidates to run when both active controls stall. The next candidate MUST
be eligible after 250 milliseconds or an earlier attempt failure. Only canonical
literals admitted by the current policy MAY be sent to the fixed native gateway.

#### Scenario: Stalled first IPv4 retains IPv6 capability

- **WHEN** the first admitted IPv4 gateway CONNECT stalls and a second admitted IPv6 destination is reachable
- **THEN** the normalizer establishes the IPv6 path within the shared deadline and forwards the exact application response
- **AND** the losing gateway control closes without receiving application bytes

#### Scenario: Another A record completes after refusal

- **WHEN** the first admitted IPv4 destination refuses and a later admitted IPv4 destination accepts
- **THEN** the request completes through the later destination without a second DNS lookup

#### Scenario: Two stalled controls do not starve a later address

- **WHEN** the first two gateway CONNECTs stall and a third admitted destination accepts
- **THEN** bounded per-attempt expiry frees a slot and the third destination completes within the original overall deadline

#### Scenario: Every attempted address remains admitted

- **WHEN** DNS returns private addresses, duplicate or mapped forms, and admitted public addresses then changes before another attempt
- **THEN** only normalized members of the original admitted snapshot are attempted and denied addresses receive no gateway request
- **AND** current policy is checked again before each literal is dispatched

#### Scenario: Exhaustion remains bounded

- **WHEN** every candidate stalls or fails, including an answer with more than eight admitted addresses
- **THEN** at most eight attempts and two simultaneous controls occur and the request fails within one connect deadline
- **AND** every attempted control closes and request capacity is restored

### Requirement: REQ-PROTO-RDB-COMMIT — One winning TCP stream without replay

The normalizer MUST select one successful gateway CONNECT before acknowledging
success to the recipient or forwarding application bytes. It MUST close all
other candidate controls before beginning the existing relay. Once a winner is
selected, any recipient, gateway or relay failure MUST terminate that stream
without starting another candidate or replaying application bytes. Cancellation
and process stop MUST reclaim all candidate sockets and existing request slots.
UDP associations MUST retain their existing single-literal binding and one-send
semantics; TCP failover MUST NOT introduce datagram retries.

#### Scenario: Winner failure never retries

- **WHEN** a selected destination receives application bytes and then closes or the recipient disconnects
- **THEN** no other destination receives those bytes and no additional CONNECT is attempted

#### Scenario: Pipelined application bytes wait for the winner

- **WHEN** the recipient sends application bytes together with its SOCKS request while two candidates race
- **THEN** those bytes reach only the committed winning destination exactly once

#### Scenario: Losing or canceled controls are reclaimed

- **WHEN** a candidate closes abruptly, another candidate wins, the recipient disconnects before a winner, or the normalizer stops
- **THEN** all losing or canceled sockets close and the worker and connection capacity return to their prior idle state

#### Scenario: UDP remains pinned

- **WHEN** a named UDP request has multiple admissible answers
- **THEN** the association selects one literal, forwards each datagram once and preserves the existing policy recheck and tuple quarantine
