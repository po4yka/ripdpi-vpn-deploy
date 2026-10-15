# audit-boundary-correctness Specification

## Purpose
Preserve exact identity, resource scope and complete artifacts across repaired project audit boundaries.
## Requirements
### Requirement: REQ-AUDIT-CLIENT — Client-bound refresh

Subscription refresh MUST match the requested client to the existing token registry entry before emission or publication, retaining the current prefix schema.

#### Scenario: Client-bound refresh

- **WHEN** a token belongs to another client or its registry match is ambiguous
- **THEN** the command refuses without emitting credentials or changing remote payloads.

### Requirement: REQ-AUDIT-GENERATION — Scoped log rotation

Xray log rotation MUST use admitted targeted recovery when the transport guard is enabled and MUST retain direct recovery for an unguarded service.

#### Scenario: Scoped log rotation

- **WHEN** Xray logs rotate while Hysteria is healthy
- **THEN** only the requested frontend recovers and failure propagates.

### Requirement: REQ-AUDIT-INSTALL — Verified installation

The release installer MUST verify the expected repository and fully qualified workflow without weakening provenance checks.

#### Scenario: Verified installation

- **WHEN** gh is available and a verified bundle is downloaded
- **THEN** the supported verifier command succeeds and failed verification prevents installation.

### Requirement: REQ-AUDIT-SELECTION — Nonempty effective verification

Verification MUST require at least one VPN host after applying the selected Ansible limit.

#### Scenario: Nonempty effective verification

- **WHEN** a limit selects only a known non-VPN observer
- **THEN** verification refuses before any acceptance claim.

### Requirement: REQ-AUDIT-PROMOTION — Single-use approval

Promotion MUST atomically validate and consume the exact approval generation under shared writer coordination.

#### Scenario: Single-use approval

- **WHEN** two callers submit the same valid approval concurrently
- **THEN** at most one starts infrastructure orchestration.

### Requirement: REQ-AUDIT-RETIRE — Declared artifact ownership

Runtime retirement MUST accept declared producer-owned metric files while refusing unrelated owners and unsafe filesystem authority.

#### Scenario: Declared artifact ownership

- **WHEN** monitoring or honeypot is disabled after its service writes a metric
- **THEN** the owned services and artifacts retire without accepting foreign files.

### Requirement: REQ-AUDIT-IPV6 — Strict IPv6 control traffic

Strict egress MUST allow required IPv6 control traffic with appropriate scope constraints while retaining its default drop.

#### Scenario: Strict IPv6 control traffic

- **WHEN** a strict host resolves a neighbor with an empty cache
- **THEN** required neighbor discovery succeeds and unrelated traffic remains filtered.

### Requirement: REQ-AUDIT-AWG — All configured AWG instances

Verification and watchdog MUST inspect and recover the normalized configured AWG instances.

#### Scenario: All configured AWG instances

- **WHEN** a named-only profile is healthy or one secondary instance fails
- **THEN** healthy instances pass and the failed exact instance is detected and recovered.

### Requirement: REQ-AUDIT-RETENTION — Effective Xray retention

Monitoring MUST install Xray log retention whenever the effective Xray service is enabled.

#### Scenario: Effective Xray retention

- **WHEN** a fresh XHTTP-only host enables monitoring
- **THEN** its Xray logs receive the same retention policy.

### Requirement: REQ-AUDIT-HOST — Diagnostic host identity

Explicit diagnostic host selection MUST reach every applicable probe and MUST NOT silently diagnose another host.

#### Scenario: Diagnostic host identity

- **WHEN** doctor or probe selects a registered host
- **THEN** host-specific commands use its address and unsupported global checks are clearly identified.

### Requirement: REQ-AUDIT-PORT — Effective recipient origin

Recipient URLs MUST use the effective configured subscription listener port, including the repository default and profile override.

#### Scenario: Effective recipient origin

- **WHEN** secrets omit subscription.port or a profile overrides the default
- **THEN** generated links and QR payloads address the actual listener.

### Requirement: REQ-AUDIT-QR — Consistent recipient bundle

Recipient pages MUST reference only current generated QR artifacts and MUST NOT retain old token QR codes after refresh.

#### Scenario: Consistent recipient bundle

- **WHEN** a bundle is regenerated without optional QR output
- **THEN** the page has no QR references and stale owned QR files are absent.

### Requirement: REQ-AUDIT-LOCK — Private shared writer lock

Secret writers MUST use compatible owner-only shared locks without following unsafe authority.

#### Scenario: Private shared writer lock

- **WHEN** rotation creates a lock under umask 022 and a Naive operation follows
- **THEN** the shared lock remains private and the next valid writer is admitted.

### Requirement: REQ-AUDIT-RELEASE — Complete release publication

A new release MUST remain draft until all required platform artifacts and checksums are available.

#### Scenario: Complete release publication

- **WHEN** one platform build or upload fails
- **THEN** the preceding complete release remains latest.

### Requirement: REQ-AUDIT-FIXTURES — Isolated synthetic authority

Synthetic Git and owner-sensitive tests MUST isolate operator identity configuration and establish the ownership they assert.

#### Scenario: Isolated synthetic authority

- **WHEN** the operator uses interactive signing or a different inherited directory group
- **THEN** fixtures exercise the intended behavior without using operator keys or relaxing production checks.

### Requirement: REQ-AUDIT-SSH — Effective bootstrap listener

First-boot SSH configuration MUST activate the configured port on service and socket-activated images before publishing readiness.

#### Scenario: Effective bootstrap listener

- **WHEN** an active SSH socket initially listens on a different port
- **THEN** units reload and the socket adopts the configured port, with activation failure withholding readiness.
