## Purpose

Deliver recipient hopping policies without silent loss while preserving atomic publication and recovery boundaries.

## MODIFIED Requirements

### Requirement: REQ-DR-HOPPING-ADMISSION — Refuse unsupported recipient hopping

RIPDPI and official sing-box export MUST retain the admitted Hysteria hopping range and interval. RIPDPI export MUST enforce the qualified client interval limits. Invalid recipient hopping MUST fail before publication. Other existing format and transport compatibility checks MUST remain effective. A failed replacement MUST preserve the prior recipient artifact; credentials MUST NOT appear in the failure result.

#### Scenario: RIPDPI recipient selects a hopping profile

- **WHEN** a selected Hysteria profile has a valid nonempty port range and format ripdpi
- **THEN** generation preserves identical port and interval semantics in standard fields and extras

#### Scenario: Replacement has an invalid interval

- **WHEN** a replacement hopping profile fails interval admission
- **THEN** generation emits no partial payload and leaves the prior published recipient artifact intact

#### Scenario: Hopping is disabled

- **WHEN** the selected profile has no hopping port range
- **THEN** the recipient keeps its fixed server port without hopping fields
