## Purpose

A revoked device credential stays unusable across rollback and share bundles, device payloads go only to hosts with a pinned identity, and removing a secrets recipient ends that recipient's access to later versions.

## ADDED Requirements

### Requirement: REQ-SEC-RPD-ROLLBACK-REVOCATION — Refuse a configuration rollback that re-admits a client

The `config` rollback action MUST refuse when a revocation is recorded for the accepted runtime, or when the previous configuration contains a client identity that the accepted configuration does not contain. The refusal MUST leave the running configuration unchanged.

#### Scenario: Previous configuration holds a removed client

- **WHEN** the accepted configuration has no entry for a client identity and the previous configuration has one
- **THEN** the rollback exits with a refusal and the accepted configuration stays in place

#### Scenario: Same client set

- **WHEN** the previous and accepted configurations hold the same client identities
- **THEN** the rollback proceeds through the ordinary transaction

### Requirement: REQ-SEC-RPD-SHARE-REVOCATION — Stop serving a share bundle when its token is revoked

After a token is revoked, the share route for that token MUST NOT return any file. A converge MUST remove every share bundle directory that is not in the declared list.

#### Scenario: Revoked token

- **WHEN** the operator revokes a token that has a share bundle
- **THEN** a request for any file of that bundle returns the same response as an unknown token

#### Scenario: Undeclared bundle

- **WHEN** a bundle directory exists on the host and is not in the declared list
- **THEN** the next converge removes it

### Requirement: REQ-SEC-RPD-PINNED-PAYLOAD-SSH — Send device payloads only over pinned SSH

An SSH call that carries a device payload MUST ignore the user's SSH configuration, MUST use strict host-key checking against the operator's pinned file, and MUST disable agent forwarding. It MUST fail before it sends data when the host key is absent or different.

#### Scenario: Unknown host key

- **WHEN** the subscription host key is not in the pinned file
- **THEN** issuance fails and no payload is sent

#### Scenario: Permissive user configuration

- **WHEN** the user's SSH configuration accepts new keys and forwards the agent
- **THEN** the issuance call still requires the pinned key and forwards no agent

### Requirement: REQ-SEC-RPD-MIRROR-IDENTITY — Pin the mirror source and separate its user

The subscription mirror MUST verify the build worker against a host key supplied in secrets and MUST refuse a first-use key. The mirror key and the backup password MUST belong to a user that is not the internet-facing service user, and the service user MUST NOT be able to read them.

#### Scenario: Mirror enabled without a host key

- **WHEN** the mirror is enabled and the host-key secret is empty
- **THEN** the role fails before it installs the mirror

#### Scenario: Service user reads the mirror key

- **WHEN** the internet-facing service user opens the mirror key file
- **THEN** the read is denied

### Requirement: REQ-SEC-RPD-DATA-KEY-ROTATION — Rotate the data key when recipients change

`rotate-secrets.sh` MUST rotate the SOPS data key in the same locked transaction as the recipient update. It MUST fail without a partial result when the rotation fails.

#### Scenario: Recipient removed

- **WHEN** the operator removes a recipient and runs the rotation
- **THEN** the file has a new data key and the removed recipient cannot decrypt it

#### Scenario: Rotation failure

- **WHEN** the data-key rotation fails after the recipient update
- **THEN** the script exits non-zero and restores the file to its state before the run
