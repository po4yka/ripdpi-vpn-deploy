## Purpose

Provide observable, testable guarantees for enforce resolved destination isolation for p0 p1 and hysteria2 across accepted inputs, successful operation, failure and retained authority.

## ADDED Requirements

### Requirement: REQ-PROTO-RDB-POLICY — Complete recipient address isolation

Every authenticated P0, P1 and Hysteria2 recipient-selected destination MUST be checked against the same documented IPv4 and IPv6 isolation policy before any connection or packet is sent. Literal address and domain representations MUST have equivalent outcomes.

#### Scenario: Public forwarding completes

- **WHEN** a synthetic authorized client requests controlled public TCP and supported UDP destinations by address and name
- **THEN** the exact pinned runtime completes the expected response without changing the destination authority

#### Scenario: Private representations are denied

- **WHEN** an authorized client selects loopback, private, link-local or unspecified destinations by literal address or a controlled hostname
- **THEN** no forbidden destination receives a connection or packet and the client gets a bounded failure

### Requirement: REQ-PROTO-RDB-DIAL — Resolution and dialing share the validated address

The address actually used for each dial, retry or UDP destination MUST remain inside the evaluated admissible set. Mixed answers and later resolution changes MUST NOT authorize a private address after an earlier public verdict.

#### Scenario: Mixed answer retains public capability

- **WHEN** the controlled resolver returns both an admissible public address and a forbidden private address
- **THEN** only an admissible address may be contacted and successful public forwarding remains possible

#### Scenario: Answer changes before retry

- **WHEN** a public answer becomes private between evaluation, retry or reconnection
- **THEN** the new address is re-evaluated or the validated address remains bound; forbidden traffic is never emitted

### Requirement: REQ-PROTO-RDB-PLUMBING — Preserve trusted resolver and adapter plumbing

The implementation MUST Destination isolation MUST preserve the documented resolver and trusted adapter paths without permitting recipients to select local management services. Rules and exceptions MUST be explicit, typed and restricted to their owning internal path.

#### Scenario: Intended adapter path succeeds

- **WHEN** a supported direct or classifier-backed profile requests a public endpoint using its normal DNS path
- **THEN** the authorized internal plumbing works and the final public request completes

#### Scenario: Recipient selects an internal service

- **WHEN** the same recipient directly names an internal resolver, classifier or management socket as its destination
- **THEN** the direct recipient request is denied while unrelated public forwarding remains usable

### Requirement: REQ-PROTO-RDB-FAILURE — Fail safely and preserve private evidence

The implementation MUST Malformed policy, unavailable resolution or unsupported runtime semantics MUST refuse before live policy activation. Failure and rollback MUST preserve the last accepted runtime and emit only categorical, bounded diagnostics without credential values.

#### Scenario: Invalid candidate preserves accepted policy

- **WHEN** a candidate isolation configuration fails its exact pinned parser or positive capability check
- **THEN** the accepted configuration remains usable and no weaker fallback is activated

#### Scenario: Failure diagnostics stay private

- **WHEN** synthetic secret-bearing configuration or resolver failure reaches validation and runtime tests
- **THEN** captured output contains no credential material and public capability resumes after accepted rollback
