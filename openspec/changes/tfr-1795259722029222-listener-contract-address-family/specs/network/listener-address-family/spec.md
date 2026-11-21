## Purpose

Define the address family of each public listener so that the provider firewall, the node ruleset and the live verifier open the same families.

## ADDED Requirements

### Requirement: REQ-LISTENER-FAMILY-FIELD — State the family in the listener contract

The implementation MUST accept an optional `family` field with the values `ipv4`, `ipv6` and `dual` on each `public_listeners` entry, and MUST treat an absent field as `dual`.

#### Scenario: Invalid family value

- **WHEN** an entry states a family other than `ipv4`, `ipv6` or `dual`
- **THEN** Terraform variable validation refuses the plan

### Requirement: REQ-LISTENER-FAMILY-LAYERS — Open only the stated family at every layer

The implementation MUST open a single-family listener only on that family in the provider firewall and in the node nftables ruleset.

#### Scenario: IPv4-only listener

- **WHEN** an entry states `family = "ipv4"`
- **THEN** the provider firewall has no IPv6 rule for it, and the node ruleset accepts it only with `meta nfproto ipv4`

### Requirement: REQ-LISTENER-FAMILY-AGREEMENT — Refuse disagreement between layers

The implementation MUST refuse a deploy when the runtime manifest family differs from the Terraform contract, and the live verifier MUST report an accept on a family that the contract does not state.

#### Scenario: Live accept on the closed family

- **WHEN** the live ruleset accepts IPv6 traffic for a listener whose contract states `ipv4`
- **THEN** `security-verify` reports a violation for that listener
