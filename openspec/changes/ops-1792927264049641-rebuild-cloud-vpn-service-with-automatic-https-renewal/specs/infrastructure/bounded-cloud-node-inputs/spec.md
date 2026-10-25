## Purpose

Provision current small cloud nodes with explicit storage, purpose and network ownership within an approved budget.

## ADDED Requirements

### Requirement: REQ-BCNI-SIZE — Exact current plan and disk

The implementation MUST admit the selected small Starter plans and explicit site root volume size and class. It MUST reject unsupported plan identifiers, undersized disks and implicit unbounded storage. A reviewed saved plan MUST precede creation.

#### Scenario: Small node plan

- **WHEN** an operator selects an admitted Starter SKU and matching disk
- **THEN** the provider plan contains the exact requested resources and preserves the management recovery contract.

### Requirement: REQ-BCNI-OBSERVER — Management-only observer purpose

The implementation MUST distinguish a management-only observer from a VPN node. Observer creation MUST NOT open VPN listeners or enroll the observer into the VPN fleet. It MUST preserve SSH allowlists, pinned host identity and private management. The approved fresh observer MUST have one separate encrypted 10 GB Archive backup disk; VPN nodes MUST NOT inherit that disk.

#### Scenario: Observer creation

- **WHEN** an explicit observer node is planned
- **THEN** only the declared management and observer interfaces are permitted, with no implicit public VPN or administrative listener.

#### Scenario: Independent observer management enrollment

- **WHEN** an operator bootstraps the independent observer
- **THEN** schema 3 selects an absolute fenced inventory and the explicit `observability-kuma` section, preserves source and host-key checks, and leaves the observer outside the persistent VPN fleet.

### Requirement: REQ-BCNI-PROMOTION — Fresh deployment with a cloud sentinel

The implementation MUST support first deployment through a distinct cloud sentinel, bind clean source, canonical provider state and exact SSH identities, reject tainted or deposed servers, and preserve the existing fresh protocol gate. Disposable targets MUST retain registered cleanup authority; personal devices MUST NOT serve as VPN probes.

#### Scenario: Separate transport nodes

- **WHEN** a fresh P0, P1 or P2 target selects the cloud promotion intent
- **THEN** its policy requires exactly its enabled transport profiles, creates the epoch during deployment, and accepts only the canonical installed runner and fresh real protocol results.

#### Scenario: Changed cloud scope

- **WHEN** source, target state, sentinel state or pinned access differs before installation or final proof publication
- **THEN** the controller refuses promotion and publishes no successful proof.
