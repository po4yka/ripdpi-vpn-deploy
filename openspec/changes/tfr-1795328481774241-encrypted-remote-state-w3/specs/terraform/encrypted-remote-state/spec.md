## Purpose

Define how OpenTofu state and saved plans for every infrastructure root are encrypted on the client, stored in a versioned and object-locked Backblaze B2 bucket, accessed with scoped keys, serialized between writers, migrated from local files and recovered.

## ADDED Requirements

### Requirement: REQ-STATE-ENCRYPTED — State and plans are encrypted before they leave the client

Every root MUST configure OpenTofu `encryption` for `state` and `plan` with an AES-GCM method keyed by a PBKDF2 key provider whose passphrase comes only from an environment variable. After migration each root MUST set `enforced = true` and have no `unencrypted` fallback. A stored state object MUST NOT contain resource attributes in plaintext.

#### Scenario: Object inspection

- **WHEN** the probe downloads the current state object of a migrated root
- **THEN** it reports an encrypted payload and no `resources` key at top level

#### Scenario: Missing passphrase

- **WHEN** `tofu plan` runs without the passphrase variable
- **THEN** OpenTofu fails before contacting any provider and writes nothing

### Requirement: REQ-STATE-BACKEND — One private, versioned, object-locked bucket

State MUST live in one private B2 bucket with file versions kept, Object Lock enabled with a governance default retention, and a lifecycle rule that removes hidden versions only after the retention ends. Each root and workspace MUST map to a distinct key; the production `default` workspace mapping of `scripts/terraform-env.sh` MUST be preserved. Backend files MUST NOT contain credentials. Both the default key and the workspace prefix MUST begin with `state/`.

#### Scenario: Two roots

- **WHEN** the Hetzner and Vultr roots are initialized for `ENV=prod`
- **THEN** they use distinct object keys in the same bucket

#### Scenario: Named workspace

- **WHEN** the same root is initialized for production and staging with the prefix-scoped CI keys
- **THEN** both keys resolve under `state/`, the plan identity reads each and the apply identity can lock and update each independently

#### Scenario: Credential in backend file

- **WHEN** a `*.s3.tfbackend` file contains `access_key` or `secret_key`
- **THEN** the ops repository validator fails

### Requirement: REQ-STATE-KEYS — Keys are bucket-scoped and least-privilege

The plan identity MUST be able to list and read state only. The apply identity MUST be able to list, read and write state but MUST NOT delete files or bypass governance retention. The recovery prefix MUST use a separate operator-only key that CI never holds. The operator MUST have a separate state-prefix identity with version read, list and write access for locked restore.

#### Scenario: Compromised apply key

- **WHEN** an attacker with the apply key tries to delete or overwrite an older state version
- **THEN** B2 refuses the deletion under Object Lock and the earlier version stays restorable

### Requirement: REQ-STATE-SERIAL — Only one writer per state at a time

Every state mutation, including restore, MUST acquire the same backend lock for the selected root and workspace. Migration MUST stop unless the pinned OpenTofu client proves contention, release and reacquisition with the intended CI and operator credentials. Backend locking MUST work without GitHub.

#### Scenario: Two applies queued

- **WHEN** two apply jobs for the same root start
- **THEN** the second waits for the first to finish

#### Scenario: Break-glass write

- **WHEN** GitHub is unavailable and an in-flight CI apply holds the backend lock
- **THEN** an operator restore or apply cannot change state until the CI writer releases it, after which the operator can acquire the lock without GitHub

### Requirement: REQ-STATE-MIGRATION — Local state moves exactly and reversibly

For each root and workspace the migration MUST record an encrypted backup, the resource address list, lineage and serial before the move; after the move the address list and lineage MUST be equal, the serial MUST NOT decrease, and `tofu plan` MUST show no changes. Any difference MUST stop the migration and leave the local file authoritative.

#### Scenario: Address mismatch

- **WHEN** the migrated state lists a different set of addresses
- **THEN** the migration stops, the backend reverts to local and the receipt records the difference

### Requirement: REQ-STATE-RECOVERY — Restore from versions without CI

The operator MUST be able to restore any retained state version from the MacBook with the break-glass passphrase and operator state-prefix key, without GitHub. Restore MUST refuse a version whose lineage differs from the current one unless the operator passes an explicit override.

#### Scenario: Bad apply

- **WHEN** an apply wrote a damaging state
- **THEN** `make restore-state` lists versions, restores the selected one as a new current version and the next plan matches it
