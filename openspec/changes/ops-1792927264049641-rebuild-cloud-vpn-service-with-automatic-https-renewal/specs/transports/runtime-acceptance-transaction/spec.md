## MODIFIED Requirements

### Requirement: REQ-PROTO-RTA-CANDIDATE — Validate the complete candidate before selecting it

Transport upgrades MUST stage exact pinned runtime bytes, required assets, configuration and TLS as one complete candidate. For native managed ACME, exact TLS policy and absence of supplied TLS files replace staged certificate bytes. Offline native validation MUST use an explicitly identified temporary TLS projection inside its owned lease. Live acceptance MUST use the unchanged ACME configuration, system trust, expected SNI and authenticated traffic before commit. The projection MUST NOT count as issuance or renewal evidence. Native configuration validation MUST use the staged runtime and asset authority before active runtime links are changed.

#### Scenario: Complete candidate is accepted

- **WHEN** a valid exact pinned candidate includes all required assets configuration and TLS
- **THEN** native validation succeeds and the candidate becomes eligible for bounded activation

#### Scenario: Stable upstream bytes retain an affected compiler

- **WHEN** a selected stable Hysteria or rclone binary lacks the required Go TLS fix
- **THEN** its exact stable source commit MUST be rebuilt outside managed nodes with Go 1.27.3, published with exact artifact checksums and independently reproduced; Hysteria MUST retain its application version under a distinct immutable release identity, rclone MUST retain dpkg ownership under a distinct package version, and native versions plus authenticated transport and backup restore MUST pass before acceptance

#### Scenario: Second asset or configuration fails

- **WHEN** a required asset download or native candidate validation fails after binary staging
- **THEN** all active links files and running accepted services remain on the preceding generation

#### Scenario: Fresh host has a group-writable system log directory

- **WHEN** Xray converges on a fresh host whose OS-managed `/var/log` permits group writes
- **THEN** it MUST provision its root-owned log directory at `/var/lib/vpn-xray-logs`, preserve the OS directory permissions, and keep no-follow, owner, single-link and file-mode checks for its logs; rotation, supervision and diagnostics MUST consume the same log path.

#### Scenario: Hysteria staged startup validates actual runtime

- **WHEN** a Hysteria candidate is validated before live publication
- **THEN** its actual staged binary, TLS and configuration MUST complete bounded isolated startup and authenticated readiness; YAML shape alone is insufficient and cleanup uncertainty refuses activation

#### Scenario: Native managed ACME has two honest acceptance stages

- **WHEN** a fresh Hysteria candidate uses the fixed private native ACME cache and HTTP-01 policy
- **THEN** offline validation MUST prove the exact runtime and authenticated forwarding with a temporary TLS projection, cleanup MUST complete, and live acceptance MUST prove the unmodified ACME config with system trust and expected SNI before any accepted receipt advances.


#### Scenario: Native certificate backup is checked before retention

- **WHEN** a backup contains a native managed ACME cache
- **THEN** the backup MUST restore its own full snapshot ID into private scratch and validate the exact production CA, certificate/key pair, domain, certificate metadata and account binding before retention, replication or success; this MUST NOT count as proof that the CA accepts the account key.

#### Scenario: Fresh cache recovery survives interrupted publication

- **WHEN** an authorized fresh-node recovery selects an exact snapshot and matching ACME policy
- **THEN** the actual pinned server and authenticated client MUST prove system trust, SNI and forwarding with the unchanged policy in an isolated network using a disposable normalized cache; a durable journal MUST bind that manifest, snapshot and exact old/candidate directory identities before publication; only the empty fresh live cache MAY be replaced by one same-filesystem rename, with current service ownership; retry MUST recognize the exact old or committed directory and refuse foreign state.

#### Scenario: Ordinary convergence does not adopt restored cache data

- **WHEN** ordinary convergence has no explicit fresh cache recovery intent
- **THEN** it MUST NOT recursively change cache ownership or copy restored bytes, and an incomplete cache recovery journal MUST refuse candidate admission.

## ADDED Requirements

### Requirement: REQ-PROTO-RTA-SITE-SESSION — Bound the complete first-convergence session

The controller MUST allow a 7200-second session for the complete exact-host `dry-run` or `deploy` graph on admitted small nodes. Separate SSH, native validation and transaction deadlines MUST remain in force. Source and input checks, owned-child cancellation and failure reporting MUST remain mandatory.

#### Scenario: Valid cold-node work exceeds one hour

- **WHEN** the complete first-convergence or preview graph continues beyond 3600 seconds
- **THEN** the controller MUST permit that work within the 7200-second full-site session budget with its normal source, input and runtime gates.

#### Scenario: Full-site session budget expires

- **WHEN** the full-site command exceeds 7200 seconds
- **THEN** the controller MUST stop its owned session and descendants, reclaim its private snapshots, and report failure; an incomplete preview MUST NOT authorize deployment.

### Requirement: REQ-PROTO-RTA-SECURITY — Effective runtime maintenance

Security maintenance MUST retain pinned runtime provenance and current CA
trust. Xray log rotation MUST render valid shell under Ansible whitespace
settings, retain guarded recovery and propagate errors. Required OS reboot
MUST use exact-host maintenance and retain post-reboot management and service
proof. Successful source checks alone MUST NOT accept deployment.

#### Scenario: Protected log rotation

- **WHEN** logrotate executes the protected Xray postrotate script
- **THEN** it MUST parse correctly and request admitted recovery only for an active service, preserving error status.

#### Scenario: Security rollout completes

- **WHEN** reviewed security updates are deployed
- **THEN** fresh target checks, encrypted actual configuration capture and an offsite restore MUST confirm the updated service scope.


#### Scenario: Authenticated gateway returns an independent UDP relay

- **WHEN** the reviewed Xray gateway returns an ephemeral UDP ASSOCIATE port
- **THEN** the normalizer MUST use that nonzero port at the exact configured backend IP while keeping the authenticated control socket, recipient source pinning and destination policy.
- **AND** a foreign relay address or zero port MUST refuse before UDP delivery while retaining the existing quarantine and capacity rules.
- **AND** the direct gateway MUST claim only `127.0.0.55` for TCP control and UDP relays; kernel admission MUST retain the normalizer UID, exact interface and source pool, and accept gateway responses only in conntrack reply direction. Foreign UDP socket owners on the claimed relay address MUST refuse activation.
- **AND** private generation readiness MUST parse the complete authenticated UDP reply and refuse a foreign address or zero port.

#### Scenario: REALITY requires a hybrid ClientHello

- **WHEN** the stable server requires an X25519MLKEM768 key share and the selected sing-box engine removes that share
- **THEN** P0 acceptance MUST execute the generated named-client profile with the pinned compatible Xray engine, preserve authenticated TCP and UDP plus wrong-credential refusal, and reject old P0 sentinel assignments to sing-box.

#### Scenario: IPv4 TCP IP options do not reach local handshake processing

- **WHEN** a VPN node converges the approved kernel mitigation
- **THEN** IPv4 TCP packets with IP options MUST drop before normal input acceptance, ordinary TCP without IPv4 IP options, UDP including IPv4 IP options, IPv6, and TCP-header options MUST retain their normal policy, and MPTCP MUST remain disabled wherever the kernel provides its control. This mitigation MUST NOT be reported as a kernel patch.

#### Scenario: Upgrade an accepted sentinel runtime contract

- **WHEN** an accepted P0 sentinel generation uses the previous runtime contract
- **THEN** receipt lookup and upgrade MUST authenticate its exact private files, metadata, runner, target identity and full private receipt digest without applying the new runtime parser to that history.
- **AND** new candidates and active probes MUST still require the current Xray contract; missing receipts or changed history MUST refuse before activation.
- **AND** failed probes and interrupted installation MUST restore the exact previous bootstrap bytes, modes and current generation.


#### Scenario: nftables loader lifecycle preserves enforcement

- **WHEN** the managed nftables loader stops, reloads, starts or restarts
- **THEN** stop MUST retain the loaded kernel policy, and reload/start MUST preserve independent tables and the current membership and remaining expiry of named timed sets.
- **AND** convergence MUST reload service definitions even after an interrupted unit copy, and MUST refuse remaining effective stop or post-stop commands before runtime publication.
