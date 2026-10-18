## Purpose

Preserve packet and DNS identity while making network safety checks and
profile transitions accurately reflect their accepted runtime scope.

## ADDED Requirements

### Requirement: REQ-NPC-EDGE — Admit the complete NAT return port domain

The UpCloud stateless firewall MUST admit TCP and UDP return packets for the
complete source-port domain that enabled forwarded NAT traffic can use. Guest
stateful filtering MUST remain authoritative for unsolicited input.

#### Scenario: Forwarded low and high source ports

- **WHEN** an enabled routed profile forwards source ports 3074 and 62000
- **THEN** provider rules admit their replies for IPv4 and IPv6.

### Requirement: REQ-NPC-TUN — Refuse partial capture as a full-device kill-switch

The strict kill-switch checker MUST refuse address, interface, user, or package
capture exclusions and partial inclusion policies. It MUST retain checks for
direct routes, outbound graphs, and both TUN address families.

#### Scenario: Routes excluded from the TUN

- **WHEN** a profile excludes default routes or selected apps from capture
- **THEN** the checker refuses full-device certification.

### Requirement: REQ-NPC-CERT — Verify enabled certificate authorities

Certificate preflight MUST validate configured identity, dates, key match,
server-auth purpose, and trusted issuer chain for each enabled TLS transport.
It MUST not require certificate material for disabled transports. Diagnostics
MUST not print private certificate or key material.

#### Scenario: Untrusted or unusable certificate

- **WHEN** an enabled transport supplies an untrusted, future, expired,
  wrong-purpose, wrong-name, or mismatched-key certificate
- **THEN** preflight refuses the candidate.

#### Scenario: Optional transport is disabled

- **WHEN** Naive is disabled and its certificate block is absent
- **THEN** complete valid enabled transport material can pass preflight.

### Requirement: REQ-NPC-RESOLVER — Reverse managed DNS-Morph transitions

DNS-Morph retirement MUST release its listener before restoring an owned
systemd-resolved stub symlink. Custom resolver authority MUST remain unchanged.
Check mode MUST not mutate resolver state.

#### Scenario: Enable and disable DNS-Morph

- **WHEN** a managed stub host enables DNS-Morph and later disables it
- **THEN** the final resolver uses the working stub after bridge retirement.

### Requirement: REQ-NPC-NAME — Preserve requested DNS identity

SOCKS name admission MUST not silently map a Unicode request to another DNS
name. Lossy Unicode forms MUST refuse and require an explicit ASCII A-label.
Existing lossless names and ASCII names MUST retain their admitted identity.
No new deployed Python dependency is required.

#### Scenario: IDNA deviation characters

- **WHEN** a Unicode request contains a sharp-s, final sigma, or joiner that
  the available codec maps to another name
- **THEN** admission refuses rather than connecting to the mapped name.

### Requirement: REQ-NPC-RELAY — Preserve TCP and UDP message lifecycles

The cascade relay MUST drain the open TCP direction after a peer half-closes.
The normalizer MUST forward permitted zero-length UDP payloads. Existing
authentication, source binding, bounds, and destination policy MUST remain.

#### Scenario: Server answers after the request FIN

- **WHEN** a client finishes sending and the server responds after EOF
- **THEN** the client receives the complete response.

#### Scenario: Empty UDP payload

- **WHEN** an authenticated association sends an admitted empty UDP payload
- **THEN** the backend receives that datagram and its reply can return.

### Requirement: REQ-NPC-HSTS — Bind HSTS to a compatible HTTPS authority

Public nginx HSTS policy MUST account for the host-wide HTTPS/443 upgrade.
An alternate-port-only hostname MUST clear the prior HSTS policy; a compatible
same-host public HTTPS/443 site MUST retain HSTS.

#### Scenario: REALITY owns port 443

- **WHEN** a public site hostname is served only on an alternate HTTPS port
- **THEN** its response does not persist an HSTS policy that redirects it to
  an unrelated REALITY identity.

### Requirement: REQ-NPC-DISCOVERY — Bound checkout metadata discovery

Checkout discovery MUST preserve NUL-delimited Git path bytes and its existing
content-filter refusal. Large metadata input MUST not create a duplex pipe
deadlock. A blocked Git command MUST remain subject to its existing deadline.

#### Scenario: Large and unusual tracked paths

- **WHEN** Git metadata exceeds pipe capacity and includes non-UTF-8 path bytes
- **THEN** discovery retains the exact path identity and completes or refuses
  within its command deadline without executing a content filter.

#### Scenario: Git cannot read metadata

- **WHEN** an owned Git metadata operation blocks before it reads the input
- **THEN** the command deadline terminates the operation and reports failure.

### Requirement: REQ-NPC-UDP-CHECKSUM — Preserve computed UDP checksum zero

Pinned AWG builds MUST transmit a computed UDP checksum of zero as ffff in
checksum completion and segmentation. TCP checksum behavior MUST remain
unchanged. Production and native builds MUST use the same strictly admitted
correction, and build receipts MUST bind its content to the installed binary.

#### Scenario: IPv6 UDP checksum sums to zero

- **WHEN** an authenticated AWG client sends an IPv6 UDP datagram whose
  completed checksum equals zero
- **THEN** the tunnel emits ffff and the upstream receives the datagram;
  an adjacent nonzero control also passes with no checksum errors.

#### Scenario: Corrected build replaces an existing source receipt

- **WHEN** the source commit stays fixed and the admitted correction changes
- **THEN** source-build identity changes and an old uncorrected binary cannot
  satisfy the new receipt or immutable acquisition path.

#### Scenario: Sentinel verifies its installed toolchain

- **WHEN** the offline sentinel installer publishes a corrected AWG toolchain
- **THEN** its immutable identity includes the correction and its response
  returns the exact input map required by the existing provenance caller.

### Requirement: REQ-NPC-EVIDENCE — Retain the complete audit ledger

Verification MUST account for every confirmed audit defect, including the
already integrated SAN/validity fixes and the separately owned Hysteria
transit redirect fix. Conditional split-hop reverse-path and Android DNS
attribution risks MUST remain separate from confirmed acceptance.

#### Scenario: Coordinated changes integrate

- **WHEN** the final source candidate is prepared for merge
- **THEN** each confirmed finding has a regression and integrated source
  evidence, without duplicate implementation or claimed live deployment.
