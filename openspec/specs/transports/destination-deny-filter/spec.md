# transports/destination-deny-filter Specification

## Purpose
Define how operators can deny known unsafe recipient destinations for P0, P1 and Hysteria2 at the shared egress boundary, how the deny data is admitted, and which traffic the policy does not cover.

## Requirements

### Requirement: REQ-EDF-DEFAULT-OFF — The policy is disabled unless an operator enables it

A node without an explicit enable toggle MUST keep its current recipient destination behavior and MUST NOT require deny data.

#### Scenario: Toggle is absent

- **WHEN** a profile does not enable the destination filter
- **THEN** the rendered normalizer configuration has no deny policy and a listed destination stays reachable

#### Scenario: Toggle is enabled without inputs

- **WHEN** a profile enables the destination filter and the secrets document has no pinned source or digest
- **THEN** validation refuses before any host mutation

### Requirement: REQ-EDF-ENFORCE — Listed destinations receive no connection or packet

When the policy is enabled, every recipient-selected P0, P1 and Hysteria2 destination MUST be checked before a connection or packet is sent. A listed name MUST deny the name and all of its subdomains, without regard to letter case or a trailing dot. A listed address range MUST deny literal addresses and every address that a name resolves to. The private-address isolation MUST still apply.

#### Scenario: Listed name and subdomain

- **WHEN** an authorized client requests a listed name or one of its subdomains over TCP or UDP
- **THEN** the boundary sends no connection or packet to the recipient and performs no resolution for that name

#### Scenario: Similar name is not listed

- **WHEN** an authorized client requests a name that only ends with the same characters as a listed name, without a label boundary
- **THEN** the request is not denied by the policy

#### Scenario: Listed address range

- **WHEN** an authorized client requests a literal address in a listed range, or a name for which every resolved address is in a listed range
- **THEN** no connection or packet reaches the listed addresses and the client gets a bounded failure

#### Scenario: Mixed resolution

- **WHEN** a name resolves to one listed address and one unlisted public address
- **THEN** only the unlisted address may be contacted

#### Scenario: Public destination

- **WHEN** an authorized client requests an unlisted public destination on each of the three paths
- **THEN** the request completes with the same result as when the policy is disabled

### Requirement: REQ-EDF-ALLOW — The operator allow list excludes false positives only

An allow-listed name MUST bypass the name and address-range deny decision for that name and its subdomains. It MUST NOT bypass the private-address isolation.

#### Scenario: False positive

- **WHEN** an operator allow-lists a listed name
- **THEN** the name and its subdomains are admitted

#### Scenario: Allow list and private address

- **WHEN** an allow-listed name resolves to a loopback or private address
- **THEN** the destination is denied

### Requirement: REQ-EDF-INPUT — Only pinned and valid deny data can activate

The deny data MUST come from a concrete release or commit URL with a SHA256 digest. A moving URL, a digest mismatch, malformed content or content over the documented entry limit MUST refuse the candidate. A refused or failed candidate MUST leave the accepted generation active, and rollback MUST restore the previous deny data together with the previous configuration.

#### Scenario: Moving source

- **WHEN** the source URL refers to a moving version such as `latest` or a branch name
- **THEN** validation refuses before any host mutation

#### Scenario: Corrupt download

- **WHEN** the downloaded data does not match the pinned digest
- **THEN** the candidate is refused and the accepted generation continues to serve traffic

#### Scenario: Oversized or malformed list

- **WHEN** the data exceeds the entry limit or has an invalid name or range
- **THEN** the candidate is refused with a categorical error that contains no list entry

#### Scenario: Rollback

- **WHEN** runtime acceptance of a candidate fails after the new deny data is staged
- **THEN** the previous generation returns with its previous deny data

### Requirement: REQ-EDF-CONTROL-PATHS — The list cannot break runtime acceptance

Activation MUST refuse deny data that denies the configured runtime canary, the REALITY target or another destination that runtime acceptance needs, unless the allow list excludes it.

#### Scenario: Canary is listed

- **WHEN** the deny data contains the name of the configured canary URL
- **THEN** activation refuses with a categorical error before the accepted generation stops

### Requirement: REQ-EDF-PRIVACY — Denials reveal and record no destination

A denied request MUST use the existing bounded destination failure, with no separate wire signal. Logs, diagnostics and metrics MUST NOT contain the requested name, its address or the matching entry.

#### Scenario: Denied request

- **WHEN** the policy denies a request
- **THEN** the client sees the same failure class as another denied destination, and the normalizer output contains only categorical text

### Requirement: REQ-EDF-BOUNDS — The policy has a measured resource limit

The entry limit MUST be set from a measurement on the smallest production node class, and the added normalizer memory MUST stay within the documented budget. A name decision MUST NOT scan the whole list.

#### Scenario: Maximum list

- **WHEN** the normalizer loads a list at the entry limit on the smallest node class
- **THEN** the measured added memory stays within the documented budget and existing services stay active

### Requirement: REQ-EDF-COVERAGE — Documentation states what the policy does not cover

Operator and client documentation MUST state that the policy does not apply to AmneziaWG or to traffic that a client sends directly, that it inspects only the destination that the boundary receives, and that it does not inspect encrypted content. The documentation MUST describe a client-side block for direct traffic.

#### Scenario: Operator reads the coverage limits

- **WHEN** an operator reads the destination filter reference
- **THEN** the page lists the covered paths, the uncovered paths and the client-side block procedure
