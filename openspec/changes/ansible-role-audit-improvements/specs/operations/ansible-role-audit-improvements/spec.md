## Purpose

Complete the remaining role audit opportunities with bounded storage, independent
per-device access, durable runtime intent and verifiable private acceptance.

## ADDED Requirements

### Requirement: REQ-IMP-RETENTION — Bound recipient history without resurrection

Bootstrap audit records MUST have explicit byte/archive bounds. Bootstrap-only
bearers MUST bind issuance time to their identity, enforce an intrinsic maximum
lifetime and reject legacy formats. Consumption and collection MUST serialize
through owned private authority. A monotonic retired-before fence MUST be
committed durably before marker removal. Admission MUST reject retired issuance
regardless of restored metadata, changed lifetime settings or wall-clock rollback.
Marker capacity MUST be bounded without removing unexpired consumption authority.
Unknown/unsafe state MUST refuse before deletion. Subscription bearers are unchanged.

#### Scenario: Restore a collected consumed grant

- **GIVEN** a consumed grant has expired and its marker is collected after the retirement fence commits
- **WHEN** an older mirror/restic generation or altered expiry metadata is restored, or the clock moves backward
- **THEN** the old URI remains refused and bounded audit/marker state survives restart

#### Scenario: Capacity and interrupted collection

- **WHEN** unexpired markers fill capacity, collection is interrupted or state is unsafe
- **THEN** no valid consumption record is discarded; admission refuses safely and prior authority remains usable

### Requirement: REQ-IMP-ACTIVATION — Reconcile interrupted desired state

Managed nginx and geodata publication MUST retain durable desired-versus-activated
identity under their existing resource lock. Retrying unchanged desired bytes
MUST activate any pending or missing receipt only after complete validation.
Activation receipts MUST become current only after successful runtime adoption;
failure MUST retain pending intent and preserve compensating publication. Known
interrupted journals MUST restore/reactivate complete prior authority or roll
forward only an exactly matching complete desired target under the same lock.
Foreign/malformed/unknown journals MUST refuse without deletion.

#### Scenario: Controller dies between publication and activation

- **WHEN** the publishing process dies after desired bytes are installed but before adoption or receipt publication
- **THEN** the next unchanged convergence validates, activates and records the desired generation; a third convergence is idempotent

### Requirement: REQ-IMP-TLS-CONCURRENCY — Isolate self-steal TLS publication

Self-steal TLS validation MUST retain its seven-day certificate floor without
shared staging. Immutable pair/pointer/vhost publication and owned retirement
MUST use the existing serialized nginx transaction. Check mode MUST be predictive
and must not publish credentials. A controller MUST NOT clean another run's state.

#### Scenario: Interleave rotation and retirement

- **WHEN** two rotations or rotation and disable overlap, or validation/activation fails
- **THEN** only a complete validated pair becomes active; cleanup is private and failed publication preserves prior authority

### Requirement: REQ-IMP-DEVICE-AUTH — Independently issue and revoke Naive clients

Naive secrets MUST expose a per-device collection with unique device names,
usernames and strong independent passwords; the old scalar pair MUST be rejected.
The exact pinned Caddy composite MUST accept each enabled client. Issuance and
revocation MUST update the encrypted document atomically through existing locking,
redaction and registry contracts. Exported material MUST select one device.
Revoking a device MUST remove its access while preserving another device's access.
An empty collection after last-device revocation MUST serve only the decoy and
MUST NOT create an unauthenticated forward proxy.
No real credential issuance is required for source validation.

#### Scenario: Two devices and one revocation

- **WHEN** two independently issued synthetic clients connect and one is removed
- **THEN** both initially authenticate, only the removed client is subsequently denied, and the other still completes real CONNECT traffic

### Requirement: REQ-IMP-METRICS — Preserve complete observations and tail recovery

Policy tailing MUST recover from same-inode truncation and inode replacement
without missing subsequent records or counting retained history twice. Honeypot
observation totals MUST include all admitted events independently of bounded logs;
suppressed logs and busy-worker drops MUST remain distinguishable. Monitoring
MUST reject wildcard/public/hostname/injected listeners before mutation and admit
only validated loopback or explicitly approved local Tailnet endpoints. Sender
scraping and verification MUST consume the same normalized endpoint.

#### Scenario: Truncate, rotate and exceed the logging cap

- **WHEN** logs are truncated/replaced and honeypot traffic exceeds its cap
- **THEN** new policy records are consumed, observation counts remain accurate and output/storage remain bounded

#### Scenario: Private endpoint agreement

- **WHEN** a listener override is approved or rejected in ordinary/check mode
- **THEN** approved sockets/scrapes agree; rejected input changes no runtime authority

### Requirement: REQ-IMP-RECOVERY-INTENT — Durably retry recovery notification

Recovery notification intent MUST persist independently of incident health and
canary freshness. Failed delivery MUST remain retryable at a bounded interval
through fresh pulses and process restart. Only confirmed matching delivery MUST clear
intent; stale completions MUST not discard a newer event. Known completed
recovery MUST not repeatedly deliver; ambiguous external acknowledgement may
require at-least-once retry. Private notification
credentials and replay/generation invariants MUST remain unchanged.

#### Scenario: Healthy pulses follow failed recovery delivery

- **WHEN** recovery delivery fails and fresh pulses/canaries continue through restart
- **THEN** durable intent retries and clears once successful without reopening or losing incident authority

### Requirement: REQ-IMP-AUDIT-GATE — Require actual successful opt-in collection

Default security reporting MUST remain non-blocking. Opt-in acceptance MUST
require enabled available successful Lynis execution and a fresh structurally
valid machine report without warning records. Missing, failed, skipped, stale,
malformed or warning-bearing collection MUST NOT count as clean acceptance.
Check mode MUST distinguish prediction from collection evidence.

#### Scenario: Scanner availability and warning output

- **WHEN** collection is disabled/unavailable/nonzero or its report is stale/malformed/contains actual warning records
- **THEN** opt-in acceptance refuses; default reporting retains its documented non-blocking behavior

### Requirement: REQ-IMP-ACCEPTANCE — Preserve prior fixes and prove positive behavior

F43 WARP tests MUST execute actual role success, repeated convergence, failure
and recovery instead of changing an invented counter. I01-I06 corrections and
qualifications MUST remain explicit, including the supported DNS boundary and
unavailable full morphology artifact. All new behavior MUST have positive and
boundary evidence, reviewed snapshots, independent review, the complete local
gate and exact-source hosted checks in existing PR 282. Synthetic fixtures MUST
NOT be represented as provider, live client or vendor-registration acceptance.

#### Scenario: Review source extension

- **WHEN** the improvement extension is prepared for PR 282
- **THEN** I07-I15 and F43 have per-ID evidence, P1/P2 regressions remain intact and source/native/CI results are separated from live acceptance
