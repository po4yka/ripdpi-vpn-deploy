# Change: Execute Path A recovery and resume after interruption

Task ID: `OPS-1792678016174902`

## Why

The recovery command currently prints a manual recipe and exits unsuccessfully in
real mode. A lost disposable node needs an executable replacement workflow whose
next invocation reconciles external outcomes after controller failure.

## What Changes

- Execute reviewed replacement provisioning, authenticated management bootstrap,
  full deployment and authenticated transport/client acceptance from Git and SOPS.
- Retain private, durable intent before each operation and reconcile current
  provider and guest state before continuing after interruption.
- Pause with a concrete action when a new host key or a changed deployment plan
  requires operator authentication or review; never synthesize those approvals.
- Support surviving publication authority through the device migration contract.
  Lost co-located publication authority requires a separately reviewed recovery
  input and must never be reported as restored from server convergence alone.
- BREAKING: real Path A requires an explicit versioned private recovery manifest;
  the old argument-only invocation is insufficient mutation authority.
- Keep emergency rescue and root restic restoration outside this Path A change.

## Capabilities

### New Capabilities

- `operations/executable-recovery`: executable replacement and crash-resumable
  recovery with exact resource, source, credential and publication bindings.

### Modified Capabilities

None.

## Impact

- Operator scripts and canonical Make surface; existing Terraform, cloud-init,
  Ansible, bootstrap and device migration contracts remain the owning executors.
- New private local plan/journal schema and focused interruption regressions.
- Source delivery through PR; no live infrastructure or credential use is part
  of implementation validation.
