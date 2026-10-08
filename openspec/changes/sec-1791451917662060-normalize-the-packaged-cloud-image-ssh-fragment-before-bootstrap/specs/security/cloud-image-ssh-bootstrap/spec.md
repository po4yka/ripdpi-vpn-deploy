## Purpose

Normalize the exact packaged cloud image SSH fragment so supported fresh nodes
can complete bootstrap without admitting unknown SSH configuration.

## ADDED Requirements

### Requirement: REQ-IMAGE-OWNER — Consume the exact packaged owner

Bootstrap MUST consume `60-cloudimg-settings.conf` only when it is a safe,
root-owned regular file with canonical mode and exact bytes
`PasswordAuthentication no\n`. Successful normalization MUST leave the canonical
10/20/50 layout and effective password, keyboard and root authentication disabled.

#### Scenario: Supported fresh image

- **WHEN** the exact packaged fragment accompanies the cloud-init fragment
- **THEN** bootstrap removes the redundant image owner, validates effective SSH
  policy and supports an unchanged successful repeat.

### Requirement: REQ-IMAGE-REFUSAL — Preserve refusal before writes

Bootstrap MUST refuse unknown fragments, changed packaged content, unsafe files
and symlinks before publishing any configuration or completion marker.

#### Scenario: Modified packaged owner

- **WHEN** the packaged fragment enables authentication or adds any directive
- **THEN** bootstrap refuses and preserves all original files.

### Requirement: REQ-IMAGE-ROLLBACK — Restore and recover the image owner

Ordinary publication or validation failures MUST restore the packaged fragment
alongside all attempted canonical writes. Process interruption MUST permit a
fresh safe repeat without accepting an unsupported residue or weakening policy.

#### Scenario: Validation failure after removal

- **WHEN** effective SSH validation fails after the packaged file is removed
- **THEN** its exact content, permissions and ownership are restored.

#### Scenario: Process death at removal

- **WHEN** bootstrap dies after removing the exact packaged file
- **THEN** a repeat completes the canonical policy and remains idempotent.
