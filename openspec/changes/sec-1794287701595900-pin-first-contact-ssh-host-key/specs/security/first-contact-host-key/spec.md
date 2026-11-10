## Purpose

Define how the operator trusts the SSH host key of a new node at the first connection, so that an attacker on the network path cannot substitute a key and receive the first deployment.

## ADDED Requirements

### Requirement: REQ-FIRST-CONTACT-PIN — Pin the host key before the first connection

The implementation MUST make the first SSH connection to a new node with strict host key checking against a public key that the operator held before the node existed.

#### Scenario: Seeded node presents its seeded key

- **WHEN** bootstrap readiness contacts a node that was created with a host key seed
- **THEN** the connection uses a private known_hosts file that holds only the seeded public key, with `StrictHostKeyChecking=yes`

#### Scenario: Presented key differs from the pin

- **WHEN** the host at the node address presents a key that differs from the seeded public key
- **THEN** readiness refuses before any remote command runs and reports a categorical host-key mismatch

### Requirement: REQ-FIRST-CONTACT-NO-TOFU — Remove trust on first use from production bootstrap

The implementation MUST NOT accept an unknown host key on any production bootstrap path without an explicit operator acknowledgement for that run.

#### Scenario: Provider without a proven seed path

- **WHEN** an operator bootstraps a node on a provider root that has no proven seed path and gives no acknowledgement
- **THEN** bootstrap refuses before the first SSH connection

#### Scenario: Operator acknowledges an unpinned first contact

- **WHEN** the operator passes the unpinned-first-contact acknowledgement for that run
- **THEN** bootstrap continues, and the run output and the node's enrollment record state that the first contact was unpinned

### Requirement: REQ-FIRST-CONTACT-SEED-PRIVACY — Keep host key material out of shared records

The implementation MUST keep the host private key and the seed image out of Git, Terraform variables and outputs, and cloud-init `user_data`.

#### Scenario: Plan and user_data inspection

- **WHEN** a plan for a seeded node is rendered
- **THEN** it contains the seed image path, the image digest, the filesystem UUID and the public key digest, and no private key bytes

### Requirement: REQ-FIRST-CONTACT-SEED-CLEANUP — Own the seed storage for the whole node lifecycle

The implementation MUST include the seed storage in the exact resource set that destroy and cleanup authorize, and MUST prove its absence after destroy.

#### Scenario: Node destroy

- **WHEN** a seeded node is destroyed
- **THEN** the destroy plan names the seed storage by its exact identifier and the post-destroy evidence records its absence

### Requirement: REQ-FIRST-CONTACT-PROVIDER-EVIDENCE — Enable a provider only on staging evidence

The implementation MUST enable the seed path on a provider root only after a disposable staging run on that provider shows a pinned first contact and an exact cleanup.

#### Scenario: Provider cannot attach a private disk at creation

- **WHEN** the staging run shows that the provider cannot attach a private seed disk before the first boot
- **THEN** that provider root keeps the refusal of REQ-FIRST-CONTACT-NO-TOFU and its documentation states the limit
