## Purpose

Select the intended supported base image for disposable Vultr nodes without
changing deployed instances or weakening provisioning and network validation.

## ADDED Requirements

### Requirement: REQ-VULTR-DEBIAN13-ID — Correct Debian 13 selection

Terraform MUST accept provider OS ID 2625 for Debian 13 x64, and the production
and staging examples MUST select it. OS ID 2284 MUST NOT be labeled Debian 13.

#### Scenario: Debian 13 node plan

- **WHEN** a valid node configuration selects OS ID 2625
- **THEN** the plan selects that exact OS ID on the Vultr instance
- **AND** SSH ownership, port, provider allowlist and DNS opt-in contracts remain enforced.

#### Scenario: Unsupported image

- **WHEN** a configuration selects an ID outside the approved allowlist
- **THEN** validation refuses the plan before creating a node.

#### Scenario: Formerly mislabeled Rocky Linux input

- **WHEN** a configuration selects OS ID 1869, which is Rocky Linux 9
- **THEN** validation refuses it because the runtime stack supports Debian and Ubuntu.

### Requirement: REQ-VULTR-IMAGE-CHANGE-ISOLATION — No implicit live migration

Updating the examples and image allowlist MUST NOT perform a provider write or
alter an existing node. Live acceptance MUST separately verify the actual
created OS and strict SSH foundation on the authorized disposable replacement.

#### Scenario: Local validation

- **WHEN** mock-provider image tests execute
- **THEN** no real instance is provisioned and no client traffic proof is claimed.

#### Scenario: Failed live foundation

- **WHEN** a replacement fails its strict foundation gate
- **THEN** its runtime deployment remains unaccepted and the original node remains available.
