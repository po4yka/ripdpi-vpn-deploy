## Purpose

Define observable guarantees for resolved destination isolation in P0, P1 and Hysteria2 across accepted inputs, successful operation, failure and retained authority.

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

#### Scenario: New UDP domains retain both address families

- **WHEN** one authenticated UDP association changes between distinct public IPv4-only and IPv6-only names, with denied names between successful requests
- **THEN** every named packet resolves to an admitted canonical literal and public completion remains possible in both families
- **AND** IPv4-mapped representations receive the same normalized policy outcome

#### Scenario: Named UDP streams retain their validated binding

- **WHEN** an association repeats a canonical name and port whose admitted literal remains bound
- **THEN** each packet rechecks that literal and forwards exactly once without a fresh DNS transaction for every packet
- **AND** DNS changing to a private answer cannot redirect the existing binding to private space
- **AND** a fresh association or target binding resolves and rejects the private answer

#### Scenario: Accepted active streams outlive five minutes

- **WHEN** accepted TCP and UDP traffic remains active beyond five minutes
- **THEN** forwarding continues within bounded connection and work limits
- **AND** only accepted traffic refreshes the configured idle timer

#### Scenario: Closed UDP associations cannot contaminate new recipients

- **WHEN** delayed frontend or upstream packets from a retired SOCKS relay association continue after its control closes
- **THEN** both socket tuples remain quarantined until the required continuous quiet interval
- **AND** no delayed packet reaches a later association, including one requesting the same destination
- **AND** resource exhaustion produces bounded refusal without forced tuple reuse

#### Scenario: Paired processes recover after normalizer loss

- **WHEN** the normalizer process dies and loses its in-memory association state
- **THEN** both old gateway generations stop before any new association is admitted
- **AND** enabled owned frontends recover automatically after the accepted guarded generation is ready

#### Scenario: Answer changes before retry

- **WHEN** a public answer becomes private between evaluation, retry or reconnection
- **THEN** the new address is re-evaluated or the validated address remains bound; forbidden traffic is never emitted

### Requirement: REQ-PROTO-RDB-PLUMBING — Preserve trusted resolver and adapter plumbing

Destination isolation MUST preserve the documented resolver and trusted adapter paths without permitting recipients to select local management services. Rules and exceptions MUST be explicit, typed and restricted to their owning internal path.

#### Scenario: Intended adapter path succeeds

- **WHEN** a supported direct or classifier-backed profile requests a public endpoint using its normal DNS path
- **THEN** the authorized internal plumbing works and the final public request completes

#### Scenario: Recipient selects an internal service

- **WHEN** the same recipient directly names an internal resolver, classifier or management socket as its destination
- **THEN** the direct recipient request is denied while unrelated public forwarding remains usable

#### Scenario: Recipient DNS preserves the guarded destination authority

- **WHEN** a recipient requests TCP or UDP DNS at a public authority, including non-address records
- **THEN** the requested authority receives the request through the same guarded destination path
- **AND** private-only DNS destinations fail while mixed answers retain admissible public capability
- **AND** engine DNS remains a distinct trusted path without a recipient-selectable local resolver bypass

#### Scenario: Owned public management addresses remain isolated

- **WHEN** a recipient selects this node's public or floating endpoint at an effective SSH, recovery or control port
- **THEN** management receives no connection or packet
- **AND** remote public SSH and the node's public web paths remain available

#### Scenario: Late packet rewriting cannot bypass isolation

- **WHEN** an admitted OUTPUT rule rewrites a public destination to a forbidden address after earlier ACCEPT verdicts
- **THEN** final policy rejects the TCP/UDP packet before the forbidden receiver observes it
- **AND** unsupported later mutation or offload authority refuses activation

#### Scenario: WARP TCP and UDP retain the isolation boundary

- **WHEN** the supported WARP path carries public TCP or UDP, including a changed destination inside one UDP association
- **THEN** the isolated gateway applies the same final address policy and only the verified owned tunnel carries admissible recipient packets
- **AND** losing the tunnel produces bounded failure without plaintext underlay fallback
- **AND** owned kernel/runtime fixtures remain distinct from separately authorized actual vendor acceptance

### Requirement: REQ-PROTO-RDB-FAILURE — Fail safely and preserve private evidence

Malformed policy, unavailable resolution or unsupported runtime semantics MUST refuse before live policy activation. Failure and rollback MUST preserve the last accepted runtime and emit only categorical, bounded diagnostics without credential values.

#### Scenario: Invalid candidate preserves accepted policy

- **WHEN** a candidate isolation configuration fails its exact pinned parser or positive capability check
- **THEN** the accepted configuration remains usable and no weaker fallback is activated

#### Scenario: Failure diagnostics stay private

- **WHEN** synthetic secret-bearing configuration or resolver failure reaches validation and runtime tests
- **THEN** captured output contains no credential material and public capability resumes after accepted rollback


#### Scenario: Running identities retain packet guard authority

- **WHEN** a systemd override runs a protected gateway or frontend with a different process UID
- **THEN** actual process UID validation refuses generation admission and stops the owned invalid process
- **AND** a correctly configured dedicated identity retains public TCP and UDP completion

#### Scenario: Reboot restores guard before recipient admission

- **WHEN** a stopped accepted generation loses its ephemeral owned kernel table
- **THEN** its controller restores and verifies only the accepted policy before starting any gateway or frontend
- **AND** unsupported foreign hook or offload state remains a bounded refusal

#### Scenario: First upgrade never retains an unguarded fallback

- **WHEN** selected legacy frontend units exist without a guarded accepted receipt
- **THEN** candidate publication first stops and disables those exact owned units
- **AND** a failed unaccepted candidate cannot restore their boot activation as an unsafe fallback

#### Scenario: Newly added WARP failure retires isolated vendor authority

- **WHEN** adding WARP fails and the accepted snapshot contains no WARP gateway
- **THEN** the owned candidate vendor and namespace are retired before removing their isolation files
- **AND** the vendor remains masked and disabled while registration state and unrelated resources remain intact
