## Purpose

Define the capability bound of the transport generation controller, so that a defect in the controller cannot use root capabilities that its operations do not need.

## ADDED Requirements

### Requirement: REQ-GENERATION-CAPABILITY-BOUND — Bound the controller capabilities

The implementation MUST set a `CapabilityBoundingSet` on `ripdpi-transport-generation.service` that lists only capabilities that a controller operation needs, and the role note MUST state the operation that needs each one.

#### Scenario: Rendered unit

- **WHEN** the unit template is rendered
- **THEN** it contains a `CapabilityBoundingSet` line, and each capability on it has a reason in the role note

### Requirement: REQ-GENERATION-CAPABILITY-OPERATIONS — Keep every controller operation working

The implementation MUST pass the native acceptance of every controller operation under the bounded unit: unit control, the UID drop for frontends, nftables restore after a reboot and the WARP namespace refresh.

#### Scenario: Reboot recovery under the bound

- **WHEN** a node with the bounded unit reboots
- **THEN** the controller restores the nftables state and starts every enabled frontend without a capability error in its journal
