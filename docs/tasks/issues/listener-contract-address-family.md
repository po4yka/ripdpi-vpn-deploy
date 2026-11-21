---
id: TFR-1795259722029222
title: Add an address family to the public listener contract
kind: feature
status: doing
area: terraform
priority: medium
risk: high
owner: po4yka
parent: null
blocked_by: []
spec_mode: required
openspec_change: tfr-1795259722029222-listener-contract-address-family
created: 2026-11-21
updated: 2026-11-21
related_tasks: [ANS-1795163654691828]
---

## Goal

Each public listener states its address family once, in the Terraform `public_listeners` contract, and the provider firewall, the node nftables ruleset and the live verifier open only that family. Follow-up of the fleet audit change `ANS-1795163654691828`, which declined a node-only family restriction because it would disagree with the provider firewall and the verifier.

## Acceptance criteria

- `public_listeners` entries accept `family` (`ipv4`, `ipv6`, `dual`); an absent field means `dual` and changes nothing.
- Every provider root opens only the stated family, with mock-provider tests.
- The listener contract check refuses a manifest family that differs from the contract.
- The node ruleset and the live verifier follow the stated family.
- A disposable staging node refuses the closed family at the provider and on the node.
