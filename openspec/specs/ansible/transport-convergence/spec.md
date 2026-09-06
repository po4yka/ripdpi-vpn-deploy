# ansible/transport-convergence Specification

## Purpose
Transport and defensive services converge into a correct, observable state: rendered WireGuard hook configuration parses, egress activation is health-gated on a verified tunnel, co-resident services can read shared TLS material, scheduled pulls preserve service state, instance config changes apply through a safe lifecycle verb, dry-runs complete under check mode, revocation matching tolerates hex case, rendered configs are well-formed, declared unit dependencies resolve, and per-connection resource hold time is bounded.
## Requirements
### Requirement: REQ-WG-HOOK-PARSEABLE — WireGuard hook configuration MUST be parseable by wg-quick

Rendered `*.conf` templates for wg-quick interfaces MUST contain only physical-line directives; no PostUp/PostDown value MAY rely on backslash line continuations, and every non-directive fragment MUST NOT be passed to `wg setconf`.

#### Scenario: bring-up on Node B

- **WHEN** `wg-quick up <iface>` runs against the rendered split-hop-egress configuration
- **THEN** parsing succeeds, all embedded nftables setup commands execute, and the interface reaches active state

### Requirement: REQ-EGRESS-HEALTH-GATE — Egress activation MUST require verified tunnel health

The WARP trace verification MUST fail when either the HTTP probe fails or the trace payload does not report an active tunnel; success of the HTTP request alone MUST NOT satisfy the gate.

#### Scenario: proxy answers while tunnel is down

- **WHEN** the SOCKS probe returns exit code 0 but the trace body reports an inactive tunnel
- **THEN** the play fails and outbound routing is not swung onto the tunnel path

### Requirement: REQ-SHARED-TLS-READABLE — Co-resident services MUST read shared TLS material

When TLS material sharing is enabled, the consuming service identity MUST be granted read access to the shared certificate and key files before the service starts.

#### Scenario: first convergence with shared TLS

- **WHEN** hysteria-realm converges on a host where share_hysteria_tls is true
- **THEN** the realm service starts without permission-denied failures reading the linked certificate and key

### Requirement: REQ-MIRROR-PRESERVES-STATE — Scheduled pulls MUST preserve service-owned state outside the payload tree

Mirror reconciliation MUST NOT delete the revoked-hashes file, SSH known_hosts, or any other service-owned state living inside the destination tree but absent from the source.

#### Scenario: timer-driven pull after revocation

- **WHEN** the mirror timer runs following a revocation render
- **THEN** the revoked-hashes file still exists and the delivery service continues enforcing revocations

### Requirement: REQ-AWG-LIFECYCLE-RESTART — Instance config changes MUST use an inactive-safe full-apply lifecycle

The amneziawg config-change handler MUST apply changes with a verb that succeeds regardless of instance active state and reapplies interface-level configuration (address, routes), not peer-only synchronization.

The AWG acceptance toolchain MUST initialize a new command directory with its exact ownership and mode under a restrictive umask, while rejecting unsafe pre-existing directories without modifying them.

#### Scenario: peer rotation on a stopped instance

- **WHEN** credential rotation notifies the handler while one AWG instance is inactive
- **THEN** the play does not abort at handler flush and the instance converges on next start

#### Scenario: Toolchain activation under a restrictive umask

- **WHEN** the acceptance toolchain initializes a previously absent command directory under umask 077
- **THEN** the new directory receives the required mode through its ownership-checked descriptor, while unsafe pre-existing directories remain unchanged and are rejected

### Requirement: REQ-CHECKMODE-SAFE-PROBES — Read-only probes MUST execute under check mode

Firewall role probes whose results gate later conditionals MUST declare check-mode execution explicitly so plan runs complete on hosts where the probed binary exists.

#### Scenario: dry-run on UFW-preinstalled image

- **WHEN** `make dry-run` targets a host with UFW installed
- **THEN** the firewall role completes without undefined-variable errors in its UFW conditionals

### Requirement: REQ-REVOCATION-CASE-INSENSITIVE — Revocation matching MUST normalize hash case

Revoked-token ingestion and lookup MUST compare hexadecimal digests case-insensitively.

#### Scenario: uppercase operator input

- **WHEN** an operator records a revocation hash in uppercase
- **THEN** requests bearing the corresponding lowercase token hash are rejected as revoked

### Requirement: REQ-RENDERED-YAML-WELLFORMED — Rendered Hysteria configuration MUST be structurally well-formed for arbitrary conforming string values

String interpolations in YAML templates MUST be emitted quoted/encoded such that YAML-significant characters in operator-supplied values cannot alter document structure.

#### Scenario: masquerade URL containing a fragment separator

- **WHEN** the configured masquerade URL contains a `#` character
- **THEN** the rendered value remains a single scalar and the service accepts the configuration

### Requirement: REQ-UNIT-DEPS-RESOLVE — Declared systemd unit dependencies MUST exist

Service units MUST reference only target/unit names that the role installs or that exist in the pinned base images.

#### Scenario: batch lifecycle operation

- **WHEN** an operator issues start/stop against the declared target of the amneziawg units
- **THEN** the operation reaches every enabled instance instead of resolving a nonexistent unit

### Requirement: REQ-BOUNDED-CONNECTION-HOLD — Defensive listeners MUST bound total per-connection resource hold time

Connection handlers MUST enforce an absolute per-connection deadline computed from acceptance time, independent of per-read activity.

#### Scenario: slow-reader slot exhaustion attempt

- **WHEN** remote peers dribble bytes to hold honeypot worker slots open indefinitely
- **THEN** each connection terminates at its absolute deadline and slots free up; exhaustion events are observable
