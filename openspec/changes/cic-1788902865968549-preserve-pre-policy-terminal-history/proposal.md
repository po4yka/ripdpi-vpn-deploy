# Change: Preserve pre-policy terminal history

Task ID: `CIC-1788902865968549`

## Why

The committed-review rule was introduced after an existing High task had
already completed through the then-valid direct terminal transition. Applying
the current rule retroactively makes that record permanently unpurgeable, while
trusting only the terminal revision's config would let a later policy downgrade
bypass the rule.

## What Changes

- Version committed-review enforcement in the repository project contract.
- Evaluate enforcement from the complete first-parent configuration ancestry
  of the terminal revision, so activation is monotonic.
- Preserve pre-activation terminal history while rejecting post-activation
  downgrade attempts.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `ci/task-contract-validation`: terminal history validation uses monotonic,
  revision-bound committed-review policy activation.

## Impact

- Affects only the repository task lifecycle config, validator, documentation,
  and regression tests. It does not change runtime infrastructure, deployment,
  secrets, or external evidence requirements.
