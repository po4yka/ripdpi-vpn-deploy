## Purpose

Prove the service IPv4 rotation cycle on real provider infrastructure and a real client device.

## ADDED Requirements

### Requirement: REQ-SIPA-STAGING — Rotation on a staging node

A disposable staging node MUST complete attach, deploy, verify and retire of a service IPv4 generation through the documented runbook without server replacement.

#### Scenario: attach and retire

- **WHEN** the operator appends a generation, applies, renders the inventory and deploys, and later removes the old generation
- **THEN** the guest owns the new `/32`, `make verify` and `make burn-check` pass on the new client address, and the retiring plan deletes only the old address resource

### Requirement: REQ-SIPA-CLIENT — Refreshed device on the new address

A real device refreshed through its unchanged subscription URL MUST pass authenticated traffic on the new client address while management stays on the primary address.

#### Scenario: device refresh

- **WHEN** the device lifecycle refresh completes after the attach
- **THEN** the device's authenticated traffic reaches the node through the new address and SSH and Tailnet bindings are unchanged
