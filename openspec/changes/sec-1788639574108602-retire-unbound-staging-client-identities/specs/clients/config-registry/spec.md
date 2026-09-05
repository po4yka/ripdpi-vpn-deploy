## MODIFIED Requirements

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
