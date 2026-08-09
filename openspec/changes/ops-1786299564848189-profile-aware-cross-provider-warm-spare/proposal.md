# Change: Add profile-aware cross-provider warm-spare redundancy

Task ID: `OPS-1786299564848189`

## Why

The fleet uses multiple providers overall, but each logical profile is currently
single-homed. Provider-selective degradation or loss of one node can therefore
remove an entire transport class even when other tiers remain healthy.

## What Changes

- Provision one provider-independent warm spare for a critical profile.
- Bind active/spare identity and health into the existing sustained,
  multi-vantage, operator-approved promotion flow.
- Add fail-closed drift, indeterminate-evidence, rollback, and cleanup behavior.

## Capabilities

### New Capabilities

- `profile-aware-warm-spare`: Maintain and safely promote a cross-provider spare
  for a logical profile.

### Modified Capabilities

- `fleet-rotation`: Evaluate logical profile health and provider binding before promotion.

## Impact

- Affects Terraform environments, provider-neutral inventory, Ansible profile
  convergence, liveness bindings, rotation state, tests, and operator runbooks.
