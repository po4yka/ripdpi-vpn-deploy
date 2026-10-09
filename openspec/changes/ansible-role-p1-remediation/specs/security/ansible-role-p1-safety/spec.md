## Purpose

Preserve critical role authority and availability during convergence, restart,
rotation, missing state and hostile or stalled local/public inputs.

## ADDED Requirements

### Requirement: REQ-P1-XRAY — Safe log authority and activation

Xray startup MUST NOT modify arbitrary filesystem targets through runtime-owned
log entries. Rotation and geodata activation MUST use a supported operation
that restores an active listener and writable current logs.

#### Scenario: Runtime log entry substitution

- **WHEN** a log entry names an unrelated target
- **THEN** startup cannot change that target's bytes, owner or mode through privileged repair.

#### Scenario: Pinned runtime log rotation

- **WHEN** a nonempty log rotates or geodata activation runs
- **THEN** no unsupported HUP is sent and the selected active runtime is reconciled.

### Requirement: REQ-P1-SUBSCRIPTION — Fail-closed delivery authority

Subscription delivery MUST refuse absent or unsafe revocation state and MUST
keep raw bearer material out of Ansible results and diffs.

#### Scenario: Lost deny list across restart

- **WHEN** a revoked payload survives but its revocation authority is lost
- **THEN** restart does not create an empty authority or make the payload usable.

#### Scenario: Uploaded recipient bundle

- **WHEN** a synthetic bearer bundle is converged with verbose callbacks
- **THEN** its token is absent from all visible task results and diffs.

### Requirement: REQ-P1-BACKUP — Effective-profile snapshot inputs

Backups MUST include effective enabled service configuration and MUST reject
missing required inputs without adding nonexistent disabled-service paths.

#### Scenario: Narrow profile

- **WHEN** only a subset of transports is enabled
- **THEN** a real local backup, retention and integrity sequence can complete without placeholder directories.

#### Scenario: Missing enabled configuration

- **WHEN** an enabled service's required input is absent
- **THEN** backup reports failure and does not report successful integrity or replication.

### Requirement: REQ-P1-RECEIVER — Bounded TLS and authenticated replay epochs

The retained receiver MUST bound handshake, header and body work before
untrusted peers consume workers. It MUST accept only its configured generation
and maintain durable replay state bound to that generation. A deliberate
generation transition MUST accept its fresh sequence without permitting old
generation replay.

#### Scenario: Incomplete TLS peer

- **WHEN** a peer leaves its handshake incomplete
- **THEN** the peer consumes only bounded time/capacity and a valid pulse remains serviceable.

#### Scenario: Authorized new generation

- **WHEN** the configured generation changes after an older high sequence
- **THEN** sequence one in the new generation is accepted and old or mismatched generations are refused.

### Requirement: REQ-P1-WATCHDOG — Private bounded notification delivery

Watchdog notifications MUST read existing notification secrets through systemd
credentials without exporting them or placing them in argv. Notification
requests and the whole oneshot MUST have finite deadlines and retain failed
supervision state even when notification delivery fails.

#### Scenario: Stalled notification destination

- **WHEN** notification cannot finish within its request budget
- **THEN** the run publishes its failed probe state, exits and permits the next scheduled run.

#### Scenario: Process inspection

- **WHEN** a notification is in flight with synthetic credentials
- **THEN** those values are absent from argv, environment and diagnostics.

### Requirement: REQ-P1-EXISTING — Preserve integrated resolver and collector repairs

Baseline MUST preserve working resolution while changing DNS-stub ownership.
The isolated collector MUST activate new TLS/revocation authority before
acceptance without mutating public VPN nginx.

#### Scenario: Existing repairs remain effective

- **WHEN** DNS-Morph enablement changes or collector CRL material rotates
- **THEN** existing regression coverage proves resolver ordering and isolated ingress activation.
