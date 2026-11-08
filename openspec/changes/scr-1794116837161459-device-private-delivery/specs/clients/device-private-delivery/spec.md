## Purpose

Let a fleet without a subscription publisher issue and refresh `ripdpi` and `singbox` devices through one private recipient artifact.

## ADDED Requirements

### Requirement: REQ-DEVICE-PRIVATE-DELIVERY — Private artifact without a publisher

When the device manifest declares no publisher, the implementation MUST issue and refresh a `ripdpi` or `singbox` device by writing one private recipient artifact that contains the rendered profile and the device AWG and Naive configurations. It MUST NOT mint a subscription token or publish a grant, and the artifact MUST have no subscription URL.

#### Scenario: Issue without a publisher

- **WHEN** the operator plans, prepares and runs an `issue` operation with `format: ripdpi` and `publishers: []`
- **THEN** the operation completes with a private artifact whose `subscription_url` is null and whose profile and AWG configuration are usable
- **AND** no grant is recorded or published

#### Scenario: Refresh without a publisher

- **WHEN** the operator refreshes the same device with a new private output path
- **THEN** the new artifact equals the issued artifact for unchanged inputs

### Requirement: REQ-DEVICE-PRIVATE-EXPIRY — Refuse expiry without a publisher

The implementation MUST refuse a manifest that requests an expiry for delivery without a publisher, because no publisher can enforce it.

#### Scenario: Expiry without a publisher

- **WHEN** a manifest has `publishers: []` and a non-empty `delivery.expires`
- **THEN** manifest loading refuses before any encrypted intent is written

### Requirement: REQ-DEVICE-OPERATOR-INPUTS — Adopt a device with the node's operator inputs
The implementation MUST pass a node's declared operator overrides to the runtime adoption and to its certificate check, and MUST compare AWG peers as a set.

#### Scenario: Operator overrides reach the adoption
- **WHEN** a manifest node declares an owner-only `overrides` file
- **THEN** every runtime goal for that node receives those variables, with revocation variables taking precedence

#### Scenario: Operator overrides change after approval
- **WHEN** the content of a declared overrides file differs from the content that the operation was approved or journaled with
- **THEN** the approval, run and resume refuse before any further adoption

#### Scenario: Peer listing order changes
- **WHEN** the AWG tool lists the same peers in a different order before and after a probe
- **THEN** the probe treats the peer set as unchanged
