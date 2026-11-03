# Change: Deliver resumable fleet maintenance and verified operator recovery

Task ID: `OPS-1793686022000048`

## Why

The service rollout required manual recovery after connection loss, correction
of inconsistent release inputs, and private scripts to capture and verify the
operator recovery kit. These operations must be repeatable project commands.

## What Changes

- Add background existing-node maintenance with exact-plan resume and encrypted logs.
- Prepare and verify complete component release inputs before live updates.
- Audit, seal, publish and verify the private operator kit through Make.
- Connect serial rollout, restore drills, passive drift checks and bounded operator
  address changes to the existing canonical operations.
- Exercise supported engine pairs in CI and separate routine credentials from
  administrative credentials where provider permissions support that separation.
- Existing deployment and recovery admission remain mandatory. No new remote
  execution service or public administration endpoint is introduced.

## Capabilities

### New Capabilities

- `operations/fleet-maintenance`: resumable maintenance and its private recovery inputs.

### Modified Capabilities

- None. Existing low-level Make commands retain their contracts.

## Impact

Operator scripts, Make entry points, tests, CI and operator documentation change.
Ansible changes are limited to required version/policy convergence and scheduled
read-only checks. Terraform continues to own cloud resources and firewall rules.
Private configuration and credentials remain outside Git. No additional
permanent server or paid resource is required.
