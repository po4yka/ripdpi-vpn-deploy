# Change: Restore provider management isolation and provisioning

Task ID: `TFR-1791523370274374`

## Why

Provider plans accept management exposure and silently diverging bootstrap
identity. Operator policy evaluation checks no rules, and the approved Hetzner
types cannot provision replacement nodes. The six P1 audit groups require
source fixes before another deployment or recovery attempt.

## What Changes

- Enforce all policy namespaces against the exact saved plan used by make apply.
- Reject world-open management networks and TCP listener overlap with SSH.
- Protect bootstrap identity with creation-time replacement guards.
- Attach Hetzner firewall protection before boot without a migration detach.
- BREAKING: reject retired Hetzner types, unsafe management configurations and
  silent bootstrap identity edits; existing private inputs need review.
- Correct the dual-stack secondary-IP policy as a prerequisite to enforcement.

## Capabilities

### New Capabilities

- `terraform/provider-management-isolation`: provider input boundaries,
  creation-time identity, safe firewall ownership and operator policy enforcement.

### Modified Capabilities

- None; the existing UpCloud activation and return-path behavior is preserved.

## Impact

- Terraform provider roots and policies; the Make operator apply surface and
  scripts; native Terraform, policy and subprocess regression tests.
- No new production dependencies, secrets schema, Ansible runtime changes,
  resource mutations or live acceptance are included.
