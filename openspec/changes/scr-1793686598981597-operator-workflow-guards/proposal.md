# Change: Verify operator inputs and encrypted recovery

Task ID: `SCR-1793686598981597`

## Why

The service rollout exposed stale workflow instructions, inconsistent release
members and package pins, ad hoc private diagnostics and recovery checks, and
late failure on missing task tools. Operators need executable checks for these
failure modes.

## What Changes

- Add local release and package-policy checks, encrypted diagnostic capture,
  and catalog-bound kit sealing and downloaded-backup verification.
- Add continuation instructions and correct monitoring skill mode selection.
- Fail task validation early when its pinned tools are missing.

## Capabilities

### New Capabilities

- `operations/operator-maintenance`: validate release inputs, retain encrypted
  diagnostics and verify selected recovery material.

### Modified Capabilities

- None. Existing deployment, credential and resource authority is unchanged.

## Impact

Scripts, Make entry points, task-tool preflight, tests and operator instructions.
No new dependency, provider action, server deployment or credential issuance.
New commands require explicit private inputs and preserve scoped authority.
