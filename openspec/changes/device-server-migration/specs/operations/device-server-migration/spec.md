## Purpose

Move affected devices to a replacement node without silently losing access,
changing subscription URLs, or mistaking publication for client-path success.

## ADDED Requirements

### Requirement: REQ-DEVICE-MIGRATION-PLAN — Exact reviewed participant set

The controller MUST resolve distinct source/target nodes and publication hosts
through strict pinned inventory, discover all non-revoked delivered devices whose
recorded hosts include the source, and bind the complete plan, participant set,
source identities and expiry to private durable state. Unsupported or ambiguous
inputs MUST refuse before mutation. An empty set MUST be reported explicitly.

#### Scenario: A reviewed plan names active and revoked devices

- **WHEN** planning examines the encrypted authoritative registry
- **THEN** all affected delivered devices are listed, revoked/expired/unissued
  devices have explicit exclusion reasons, and no secret or bearer URL is printed.

#### Scenario: Inputs change after review

- **WHEN** a plan, selected credential, node identity or delivery generation changes
- **THEN** continuation refuses that stale review without silently skipping devices.

### Requirement: REQ-DEVICE-MIGRATION-CREDENTIALS — Target preparation with overlap

The controller MUST prepare usable device credentials for enabled target
transports while retaining source access and unrelated target devices. It MUST
preserve per-device identity, allocate collision-free target AWG addresses and
bind recovery authority to the target instance. Conflicting identities MUST
refuse; plaintext credentials MUST NOT enter journals, logs or Git.

#### Scenario: Four-transport device moves to a distinct node

- **WHEN** target preparation is accepted
- **THEN** its Xray, Hysteria and AWG device authorities can produce usable
  replacement profiles, source credentials remain intact, and unrelated users
  and target server keys retain their exact values.

#### Scenario: Preparation is interrupted

- **WHEN** the encrypted target transaction committed but its caller lost success
- **THEN** continuation recognizes the exact prepared generation or refuses a
  conflicting generation; it does not duplicate peers or allocate a second key.

### Requirement: REQ-DEVICE-MIGRATION-PUBLISH — Stable grant publication
The controller MUST retain existing tokens and expiry, use the canonical payload
materializer, and publish exact replacement bytes with compare-and-swap under
the installed subscription authority lock.

#### Scenario: Preserve publication authority during migration
- **WHEN** the controller publishes replacement delivery bytes
- **THEN** It MUST preserve revocation and
  mirror boundaries and verify every required publisher before counting publication.
  Moving a delivery host MUST preserve the reviewed subscription origin and retain
  the old publisher during overlap. Unknown remote outcomes MUST be reconciled
  against exact bytes before replay or local registry completion.

#### Scenario: Existing subscription receives the replacement

- **WHEN** a device refreshes its unchanged subscription URL after publication
- **THEN** the served payload selects the target instead of the source and retains
  unmodified alternate hosts, format, expiry and device-local AWG key semantics.

#### Scenario: Lost acknowledgement or concurrent grant edit

- **WHEN** publication committed without an acknowledgement, or another writer
  changed the expected grant
- **THEN** an exact already-published result resumes safely and a conflicting
  document refuses without overwriting it or reviving revoked/expired access.

### Requirement: REQ-DEVICE-MIGRATION-RECEIPT — Honest explicit client evidence
RIPDPI deliveries MUST carry a bounded per-delivery migration identity and secret
receipt key.

#### Scenario: Bind imported and tested evidence to one delivery
- **WHEN** a client imports a migration delivery and explicitly exports evidence
- **THEN** The client MUST hash exact received bytes, persist receipt context
  only with successful import, and export evidence only on explicit user action.
  Received and path-tested MUST remain distinct. Path-tested evidence MUST come
  from a real authenticated payload request through an exact replacement candidate
  or exact consumed AWG configuration, with no old/direct fallback. The controller
  MUST validate receipt MAC, delivery identity, raw payload digest, target tag,
  state and time, reject replay across deliveries, and never downgrade evidence.
  AWG migration MUST preserve an existing device-local private key through an
  explicit previous-to-target tag mapping within that same subscription. It MUST
  NOT search unrelated groups for a key or export the previous tag in receipts.

#### Scenario: Imported profile has not been tested

- **WHEN** the client exports after import alone
- **THEN** the receipt is received-only and cannot authorize retirement.

#### Scenario: Replacement transport passes its payload test

- **WHEN** P0, P1, Hysteria or AWG completes the exact candidate-path test
- **THEN** an explicit export can prove that candidate path without claiming
  hardware attestation, background telemetry or complete device traffic capture.

#### Scenario: Other client software requires human confirmation

- **WHEN** a preserved non-RIPDPI profile has no machine receipt implementation
- **THEN** publication remains distinct from verification and only an explicit,
  per-device, generation-bound operator confirmation with a reason can supply
  the separately labeled manual acceptance state.

### Requirement: REQ-DEVICE-MIGRATION-RETIREMENT — Resumable gated handover

Blue-green MUST use separate target secrets, prepare devices before target
convergence, publish after target verification, and refuse completed handover
while any participant lacks current accepted path evidence. The controller MUST
support repeated status, receipt import and continuation after interruption under
one stable lock. It MUST preserve old access and provide a reviewed rollback of
owned publication changes without automatic infrastructure deletion.

#### Scenario: One device remains on the old profile

- **WHEN** retirement readiness is checked after partial publication or receipt import
- **THEN** the incomplete device remains visible and blue-green cannot report the
  migration complete or suggest that the old node is safe to retire.

#### Scenario: Operator rolls publication back

- **WHEN** rollback is requested for the unchanged owned published generation
- **THEN** prior payload bytes and registry options are restored under the same
  compare-and-swap checks; conflicting external edits are preserved and reported.
