# clients/config-registry Specification

## Purpose
An encrypted per-device registry that records client configuration issuance
parameters (format, hosts, cohorts, token identity, key fingerprints) and
lifecycle state, so that every distributed artifact is reproducible from git
+ SOPS + Terraform outputs plus persisted issuance options, token refreshes
preserve the original issuance contract, and stale or lost devices are
detectable without retaining local plaintext copies.
## Requirements
### Requirement: REQ-REGISTRY-RECORD — Registry entry per issued device

The secrets document MUST contain a `clients` registry section with one entry
per provisioned device, recording: device name, issued format(s), hosts
(provider:env pairs), cohorts, token hash prefix, expiry, AWG peer public-key
fingerprint, issuance timestamp, and lifecycle status.

#### Scenario: Client onboarding creates a complete registry entry

- **WHEN** `scripts/new-client.sh` provisions a new device
- **THEN** a registry entry exists with the device name, chosen format,
  hosts/cohorts, issuance timestamp, public-key fingerprint, and status
  `issued`, and `scripts/check-secrets-coverage.py` accepts the document.

#### Scenario: Registry entry is missing required fields

- **WHEN** the secrets coverage check runs against a secrets document whose
  client entry lacks any registry field
- **THEN** the check fails naming the device and the missing field.

### Requirement: REQ-REGISTRY-LIFECYCLE — Lifecycle state transitions

The registry MUST track status transitions `issued → delivered → active →
stale | revoked | burned`, written by the same scripts that perform the
corresponding action (provisioning, token issuance, payload delivery,
fleet IP change, revocation).

#### Scenario: Token issuance advances status

- **WHEN** `issue-sub-token.sh` issues or refreshes a `/sub/` token for a
  registered device
- **THEN** the registry entry records the token hash prefix, expiry, format,
  hosts, and cohorts, and status becomes `delivered`.

#### Scenario: Fleet recreation marks devices stale

- **WHEN** a node IP changes (fleet recreation or rotation) and the operator
  runs the documented post-deploy step
- **THEN** devices bound to the changed endpoint are marked `stale`, and the
  drift check reports them until refreshed.

### Requirement: REQ-REFRESH-OPTIONS — Refresh preserves issuance options

`issue-sub-token.sh --refresh-token` MUST read the original issuance options
(format, provider/env, hosts, cohorts, SOPS files) from the registry and MUST
NOT fall back to implicit defaults for an existing token. Operator overrides
MUST be explicit and MUST be recorded in the registry and audit log.

#### Scenario: Refresh of a ripdpi multi-host token

- **WHEN** an operator refreshes a token whose registry entry records
  `--format ripdpi` with two `HOSTS` entries, passing only
  `--refresh-token <token>`
- **THEN** the regenerated payload uses the ripdpi format and both hosts, and
  the audit log entry records the reused options.

#### Scenario: Refresh of an unregistered token fails closed

- **WHEN** `--refresh-token` is passed a token with no registry entry
- **THEN** the script exits non-zero without writing any payload, and the
  error names the missing registry entry.

### Requirement: REQ-PRIVATE-KEY-RECOVERY — AWG private key stored encrypted

`new-client.sh` MUST write the generated AWG client private key into the
SOPS-encrypted secrets document (per-device field) at generation time, and
MUST NOT leave the only copy in a plaintext local artifact. The device-local
key remains the primary copy; the SOPS entry is the recovery path.

#### Scenario: Local artifact loss is recoverable

- **WHEN** all plaintext artifacts under `secrets/local/clients/<device>/`
  are destroyed after delivery
- **THEN** the AWG private key remains recoverable by decrypting the SOPS
  document, and the registry entry records the matching public-key
  fingerprint.

#### Scenario: Plaintext artifacts are disposable

- **WHEN** `new-client.sh` or `issue-sub-token.sh` finishes delivering a
  payload
- **THEN** the operator guidance (and `make clean`) treats
  `secrets/local/clients/**` as a disposable cache, and no script requires a
  plaintext local artifact to exist after delivery.

### Requirement: REQ-DRIFT-CHECK — Payload drift detection

A `make client-drift CLIENT=<name>` target MUST re-render the device payload
from current git + SOPS + Terraform outputs and compare its identity
(embedded source-identity hash and Terraform outputs hash) against the
identity recorded at last delivery, reporting `stale`, `current`, or
`unknown` without requiring the delivered file to be stored locally.

#### Scenario: Endpoint change detected as drift

- **WHEN** a node IP changes after payload delivery and the operator runs
  `make client-drift CLIENT=<device>`
- **THEN** the check reports `stale` and prints the identity delta.

#### Scenario: Unchanged fleet reports current

- **WHEN** the drift check runs with no relevant source or output change
  since last delivery
- **THEN** the check reports `current` and exits zero.

#### Scenario: Drift check without registry entry

- **WHEN** the drift check runs for a device with no registry entry
- **THEN** the check reports `unknown` with a non-zero exit and does not
  guess defaults.

### Requirement: REQ-REGISTRY-SECURITY — Registry confidentiality and revocation

The registry MUST live only inside the SOPS-encrypted document (never in
git-tracked files, never on the delivery host), and token revocation MUST append
the hash to `subscription.revoked_tokens` and set registry status to `revoked`
in the same operator action. Removal of an unbound staging-only identity MUST
require exact original intent, cleanup manifest, verified provider absence and
state-zero binding. The recovery action MUST accept only status `issued`,
remove every exact client collection entry in one serialized compare-bound
encrypted transaction, remove every matching Xray cohort reference, validate
the resulting client graph, and emit only a redacted durable receipt. The
transaction MUST use the same project lock as every supported SOPS writer.

#### Scenario: Revocation is atomic in the registry

- **WHEN** an operator revokes a device token
- **THEN** the revoked hash list and the registry status update land in one
  SOPS edit, and a subsequent payload fetch returns the revoked response.

#### Scenario: Unbound issued staging client is retired after exact absence

- **GIVEN** one client exists exactly once in every required encrypted client
  collection and has registry status `issued`
- **AND** the exact staging provider/environment/hostname is bound by the
  original intent, cleanup manifest and verified absence/state-zero evidence
- **AND** the destroyed state bytes match the path and digest bound by the
  exact cleanup manifest
- **AND** executor binding, promotion, sentinel, pending and output artifacts
  are absent
- **WHEN** the operator invokes the unbound retirement command
- **THEN** every exact client entry and Xray cohort reference is removed
  atomically and a mode-0600 terminal receipt records only request and
  ciphertext hashes

#### Scenario: Interrupted encrypted retirement is replayed safely

- **WHEN** the controller restarts with an exact matching durable journal
- **THEN** it either completes from the unchanged original ciphertext or
  verifies the exact published post-image
- **AND** foreign, partial, ambiguous or replaced state is retained and refused
  without another encrypted mutation

#### Scenario: Bound, promoted, partial or non-issued identity is refused

- **WHEN** any forbidden lifecycle artifact exists, decrypted YAML has a
  duplicate mapping key at any depth, the registry status is not `issued`,
  collection membership is partial or duplicate, an Xray cohort has duplicate
  or unknown client references, or target evidence mismatches
- **THEN** the command exits non-zero before changing the SOPS ciphertext and
  prints no plaintext or secret value

