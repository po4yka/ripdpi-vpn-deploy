## Purpose

Make current-node service maintenance survive operator connection failures while
retaining exact source, private input, authorization and recovery boundaries.

## ADDED Requirements

### Requirement: REQ-MAINT-RESUME — Resume exact maintenance operations

The controller MUST retain durable stage intent, frozen source and input hashes,
shared resource locks and an authorization deadline. It MUST run independently
of the initiating terminal, retain encrypted diagnostics and clean its owned
plaintext after success or failure. Status MUST distinguish historical completion
from fresh live verification. Resume MUST use canonical recovery admission.

#### Scenario: Connection fails during deployment

- **WHEN** a deployment loses its connection after recording mutation intent
- **THEN** the operation retains its uncertain stage and encrypted diagnostics
  and cannot skip acceptance or blindly repeat an external action.

### Requirement: REQ-MAINT-RESUME-CONVERGED — Resume a converged node at acceptance

Resume MUST skip dry-run and deploy for a node only when the journal records its completed deploy for the plan source and a fresh live manifest probe reports that source. Decrypt and every acceptance stage MUST run again. A complete sequence MUST first discard the recorded convergence. The journal MUST record each skip.

#### Scenario: Acceptance fails after a completed deploy

- **WHEN** an operation fails in verify after its deploy stage completed, and the live node still reports the plan source
- **THEN** resume runs decrypt and every acceptance stage for that node, without a second dry-run or deploy.

#### Scenario: The node cannot be observed

- **WHEN** the manifest probe fails with a transport error
- **THEN** resume runs the complete stage sequence; a local input error fails the node instead.

#### Scenario: A repeated deploy fails after the manifest is written

- **WHEN** a resume runs the complete sequence for a node with recorded convergence, and its deploy fails
- **THEN** the recorded convergence is gone, and the next resume runs dry-run and deploy again.

#### Scenario: Live node differs from the recorded convergence

- **WHEN** the recorded convergence matches the plan, but the live node manifest reports another revision or digest
- **THEN** resume runs the complete stage sequence, starting with dry-run.

### Requirement: REQ-MAINT-RELEASE — Verify complete release inputs

Release preparation MUST bind component version, architecture, HTTPS artifact,
checksum and archive members together. Verification MUST inspect the actual
checksum-verified archive and reject a missing, duplicate or unsafe member.
Package installation and package pin updates MUST use the same version.

#### Scenario: Metadata contains an old archive member

- **WHEN** a new artifact has an archive member path from an earlier version
- **THEN** preparation or verification fails before live deployment.

### Requirement: REQ-MAINT-KIT — Verify private operator recovery

The kit command MUST validate private input authority, exclude working plaintext,
seal a complete bounded manifest, verify independent downloaded ciphertext and
decrypted contents, and refuse a current-coverage claim if inputs changed.
Post-delivery acknowledgement MUST remain separate from the acknowledged payload.

#### Scenario: Configuration changes during upload

- **WHEN** a selected kit input changes after the snapshot
- **THEN** the uploaded version is retained without claiming current coverage.

### Requirement: REQ-MAINT-SERIAL — Gate each next node on acceptance

Serial rollout MUST complete canonical preview, deployment, security and required
authenticated protocol checks on one node before admitting the next node. A
failure MUST stop advancement and retain recovery information.

#### Scenario: First node fails protocol acceptance

- **WHEN** the first node deploys but its required protocol check fails
- **THEN** the second node is not changed and the first node remains unaccepted.

### Requirement: REQ-MAINT-RESTORE — Exercise scheduled recovery

Restore checks MUST download and authenticate the selected backup, compare its
manifest and check applicable application data without changing production data.
Scheduling MUST report failures or excessive backup age without repeated notices
for an unchanged healthy state.

#### Scenario: Remote backup cannot be decrypted

- **WHEN** the remote object exists but fails authenticated decryption
- **THEN** restore verification fails and reports no successful recovery.

### Requirement: REQ-MAINT-DRIFT — Report actual configuration drift

Passive checks MUST compare source-bound expected runtime, package policy,
listeners, TLS expiry and monitoring freshness against actual observations.
They MUST not repair production automatically.

#### Scenario: A package pin diverges from its installed version

- **WHEN** the expected version and installed version match but the pin differs
- **THEN** the check reports the policy difference without changing it.

### Requirement: REQ-MAINT-IP — Bound operator address changes

Address maintenance MUST require an exact resource scope and finite authorization,
confirm the address through two independent HTTPS sources and replace only the
managed single-host source. It MUST prove new access before removing old access
and preserve other rules. Expiry MUST prevent new mutations.

#### Scenario: Authorization expires before an address change

- **WHEN** the check detects a new address after authorization expiry
- **THEN** it reports required action without changing a firewall or allowlist.

### Requirement: REQ-MAINT-CI — Exercise real release consumers

CI MUST exercise the supported current client/server engine pair and release
archive contents. Local environment diagnostics MUST identify missing or wrong
pinned tools separately from behavior failures without weakening assertions.

#### Scenario: An engine update breaks authenticated client traffic

- **WHEN** the updated engine parses configuration but rejects the supported client
- **THEN** the real interoperability check fails before production rollout.

### Requirement: REQ-MAINT-CREDENTIALS — Separate routine access

Routine commands MUST receive only the credentials needed for their fixed
operations. Administrative credentials MUST require an explicit selected
administrative operation. New restricted access MUST be verified and encrypted
before existing usable access is retired; unsupported provider scoping MUST be
reported without inventing a permission guarantee.

#### Scenario: A routine backup uses a restricted storage key

- **WHEN** the backup publishes under its admitted operator prefix
- **THEN** upload and readback succeed while access outside that prefix is denied.

### Requirement: REQ-MAINT-CATALOG — Reconcile accepted core state

The controller MUST publish accepted core state only after source, protocol and
cleanup gates pass. It MUST preserve unrelated catalog data, refuse conflicting
core updates, and retain a receipt with time, source and evidence binding.

#### Scenario: Catalog publication fails after acceptance

- **WHEN** a node passes acceptance but catalog publication fails
- **THEN** resume reconciles its retained receipt before continuing and does not deploy it again.

#### Scenario: Catalog core changed after preparation

- **WHEN** a node not yet accepted by the plan no longer has its prepared core fields
- **THEN** preview, start and resume refuse before any host mutation.

### Requirement: REQ-MAINT-GENERATE — Generate exact maintenance inputs

The controller MUST generate schema-2 maintenance configuration from exact catalog
node IDs, resolve private dependency paths, and reject missing or unsafe inputs.
Generation MUST NOT create credentials, access hosts or bypass preview approval.

#### Scenario: Selected mapping is incomplete

- **WHEN** a selected node lacks a required private dependency
- **THEN** generation refuses before publishing a configuration or contacting a host.

### Requirement: REQ-MAINT-SCHEDULE — Schedule verified operations

Explicit installation MUST support Linux cron and macOS launchd. Scheduled drift
checks MUST run canonical read-only verification with encrypted diagnostics and
no automatic repair. Scheduled backups MUST use the restricted routine credential
loader and require remote download, authenticated decryption and manifest proof.
Each job MUST enforce its deadline, frozen inputs, finite timeout and overlap lock,
and publish private status that distinguishes failure, running and overdue evidence.

#### Scenario: Remote readback fails

- **WHEN** a scheduled backup uploads but cannot verify its downloaded archive
- **THEN** the job records failure and does not advance its last successful backup time.

#### Scenario: Scheduler misses a run

- **WHEN** the last successful run exceeds the configured freshness window
- **THEN** status reports overdue rather than healthy.

#### Scenario: Drift check exceeds its timeout

- **WHEN** a scheduled drift stage runs past the job timeout
- **THEN** the drift child cancels that stage and removes node plaintext before it exits.
