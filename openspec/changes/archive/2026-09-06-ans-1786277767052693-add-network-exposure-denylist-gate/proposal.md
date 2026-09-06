# Change: Add a disabled-by-default network exposure denylist gate

Task ID: `ANS-1786277767052693`

## Why

Operators need a reviewable way to reduce exposure to explicitly disallowed network ranges without embedding those ranges in source control or introducing an updater that can change live policy without review. The current firewall render has no schema, validation, or canary boundary for such policy.

## What Changes

- Add a disabled-by-default Ansible integration that validates reviewed feed metadata and separate ingress/egress policy intent.
- Add redacted dry-run and log-only review paths, fail-closed validation, explicit promotion, expiry, rollback, and monitoring criteria.
- Preserve byte-equivalent firewall output when the feature is disabled and prohibit repository-owned deployable address payloads.

## Capabilities

### New Capabilities

- `network-exposure-denylist`: Validate and review disabled-by-default network exposure policy without hidden mutation or committed address data.

### Modified Capabilities

- None.

## Impact

- Portfolio area: `ansible`; security policy is also affected.
- Expected integration surfaces: a new Ansible role, shared group variables, site playbook, firewall render contract, tests, operator documentation, and optional `vpnd` dry-run presentation.
- This proposal does not authorize live enforcement or acquisition of external address data.
