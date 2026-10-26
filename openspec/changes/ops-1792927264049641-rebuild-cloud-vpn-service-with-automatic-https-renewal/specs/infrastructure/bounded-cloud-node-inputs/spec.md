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

#### Scenario: Migrate observer SSH ownership without VPN membership

- **WHEN** the exact observer is selected for the bounded SSH ownership transaction
- **THEN** a mandatory `observability-kuma` section binds the same dual-path and rollback checks, without selecting the VPN fleet or accepting old unscoped inputs.

### Requirement: REQ-BCNI-PROMOTION — Fresh deployment with a cloud sentinel

The implementation MUST support first deployment through a distinct cloud sentinel, bind clean source, canonical provider state and exact SSH identities, reject tainted or deposed servers, and preserve the existing fresh protocol gate. Disposable targets MUST retain registered cleanup authority; personal devices MUST NOT serve as VPN probes.

#### Scenario: Separate transport nodes

- **WHEN** a fresh P0, P1 or P2 target selects the cloud promotion intent
- **THEN** its policy requires exactly its enabled transport profiles, creates the epoch during deployment, and accepts only the canonical installed runner and fresh real protocol results.

#### Scenario: Changed cloud scope

- **WHEN** source, target state, sentinel state or pinned access differs before installation or final proof publication
- **THEN** the controller refuses promotion and publishes no successful proof.

### Requirement: REQ-BCNI-UFW — Disabled packaged firewall wrapper

First enrollment MUST admit inactive UFW when its exited unit, helpers and disabled configuration match the package. Read-only preflight and runtime snapshot MUST share the check and leave UFW unchanged. Active UFW, modified files, unit overrides, diversions, pending reload and foreign kernel rules MUST refuse.

#### Scenario: Disabled provider-image UFW

- **WHEN** the provider image has an active exited UFW unit, intact package files, no overrides, diversions or pending reload, a configuration equal to the package template with exactly one `ENABLED=no`, and inactive UFW status
- **THEN** bootstrap can proceed through all existing kernel-rule, identity and transaction checks without changing that unit.

#### Scenario: Active or changed UFW

- **WHEN** UFW reports active, its package configuration differs, or its unit has not exited
- **THEN** bootstrap refuses before enrollment or access writes.

### Requirement: REQ-BCNI-DNS — Manage retained public DNS records

The Vultr root MUST manage explicitly selected A, AAAA and CNAME records in an existing zone. Empty inputs MUST leave DNS unmanaged. Existing records MUST be imported before cutover; the plan MUST preserve their IDs and MUST NOT replace the zone or the server.

#### Scenario: Publish separate web and UDP endpoints

- **WHEN** the operator supplies the web apex A/AAAA, the www CNAME and the UDP endpoint A/AAAA
- **THEN** each record retains its exact name, type, data and integer TTL, and invalid address families, conflicting names and unsupported types are rejected before mutation.

#### Scenario: Issue a cloud client for the web-only node

- **WHEN** a web-only profile retains inactive Hysteria ACME inputs during client issuance
- **THEN** those inputs do not claim HTTP/80; enabling both nginx and native Hysteria ACME still refuses the shared listener.
