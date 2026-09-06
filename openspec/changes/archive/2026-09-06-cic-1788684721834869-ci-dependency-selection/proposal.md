# Change: Select CI checks from changed-file dependencies

Task ID: `CIC-1788684721834869`

## Why

Every PR runs the full costly integration graph even when its files affect only
one consumer. Conditional scheduling must preserve fail-closed merge admission.

## What Changes

- Select the transitive consumer checks for the complete PR diff.
- Keep baseline checks unconditional and main/manual runs complete.
- Reject unexpected skips and failed or malformed dependency plans.
- BREAKING: replace individual conditional required contexts with the planner,
  strict aggregate gate and unconditional required contexts.

## Capabilities

### New Capabilities

- `ci-dependency-selection`: dependency-aware scheduling and strict admission.

### Modified Capabilities

- None.

## Impact

- GitHub CI scheduling and branch-protection required status contexts.
- No deployed Terraform, Ansible, secrets, network or public CLI contracts change.
- No new runtime dependencies. Protection migration requires green hosted proof.
