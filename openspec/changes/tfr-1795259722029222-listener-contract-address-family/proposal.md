# Change: Add an address family to the public listener contract

Task ID: `TFR-1795259722029222`

## Why

The fleet audit of 2026-11-20 found that the node accepts TCP/443 over both IPv4 and IPv6 although some transports serve only one family. The listener contract entry (`name`, `protocol`, `port`, `port_range`) has no address family, so the provider firewall, the node ruleset and the live verifier all open both families. Change `ans-1795163654691828-udp-node-audit-hardening` declined a node-only restriction, because a ruleset that disagrees with the provider firewall and the verifier makes the contract check unreliable. The field must start in `public_listeners` and flow to every layer.

## What Changes

- `public_listeners` entries gain an optional `family` field with the values `ipv4`, `ipv6` and `dual`; an absent field means `dual`, which keeps the current behaviour.
- Each provider root opens only the stated family in its firewall.
- The runtime listener manifest carries the family, and the contract check compares it with the Terraform contract.
- The node nftables ruleset accepts a listener only on its stated family, and the live verifier reports an accept on another family.

## Capabilities

### New Capabilities

- `network/listener-address-family`: the address family of each public listener and its agreement across the provider firewall, the node ruleset and the live verifier.

### Modified Capabilities

- None

## Impact

- Terraform: every provider root (variable validation, firewall rules, outputs) and the Conftest policies.
- Ansible: the listener manifest and the firewall template.
- Scripts: `check-listener-contract.py` and `verify-public-listeners.py`.
- Operator: no action for the default `dual`; a single-family listener needs a Terraform apply before the deploy.
